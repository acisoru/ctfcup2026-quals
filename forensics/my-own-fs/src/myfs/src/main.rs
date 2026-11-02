//! myfs: a tiny inode-chain filesystem.
//!
//! Device layout (N = device_size / 1338):
//!   [0, N)                      inode list: one byte per inode, 0 = free, 1 = used
//!   [N + i*1337, N + (i+1)*1337) inode i
//!
//! Inode 0 is the root directory. Every inode starts with a u32 LE pointer to
//! the next inode of the same file (0 = end of file) and a type byte.
//!
//! Head inode (first inode of a file / directory), 51 byte header:
//!   0  u32 next      4  u8  type (1 = file, 2 = dir)
//!   5  u16 mode      7  u32 uid      11 u32 gid      15 u64 size
//!   23 i64 atime     31 i64 mtime    39 i64 ctime    47 u32 nlink
//!   51 .. data
//! Continuation inode, 5 byte header:
//!   0  u32 next      4  u8  type (0)
//!   5  .. data
//!
//! Directory data is a sequence of entries: u32 inode, u8 name_len, name.

use fuser::{
    FileAttr, FileType, Filesystem, MountOption, ReplyAttr, ReplyCreate, ReplyData,
    ReplyDirectory, ReplyEmpty, ReplyEntry, ReplyStatfs, ReplyWrite, Request, TimeOrNow,
};
use rand::seq::SliceRandom;
use rand_chacha::rand_core::SeedableRng;
use rand_chacha::ChaCha20Rng;
use sha2::{Digest, Sha256};
use std::ffi::OsStr;
use std::fs::{File, OpenOptions};
use std::io;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::FileExt;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const ISZ: usize = 1337;
const HEAD: usize = 51;
const CONT: usize = 5;
const T_CONT: u8 = 0;
const T_FILE: u8 = 1;
const T_DIR: u8 = 2;
const TTL: Duration = Duration::from_secs(1);

type Res<T> = Result<T, i32>;

fn now() -> i64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64
}

fn to_time(t: i64) -> SystemTime {
    UNIX_EPOCH + Duration::from_secs(t.max(0) as u64)
}

fn from_time(t: TimeOrNow) -> i64 {
    match t {
        TimeOrNow::Now => now(),
        TimeOrNow::SpecificTime(t) => t.duration_since(UNIX_EPOCH).map(|d| d.as_secs() as i64).unwrap_or(0),
    }
}

fn rd32(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn rd64(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes(b[o..o + 8].try_into().unwrap())
}

#[derive(Clone, Copy)]
struct Stat {
    kind: u8,
    mode: u16,
    uid: u32,
    gid: u32,
    size: u64,
    atime: i64,
    mtime: i64,
    ctime: i64,
    nlink: u32,
}

impl Stat {
    fn parse(b: &[u8]) -> Stat {
        Stat {
            kind: b[4],
            mode: u16::from_le_bytes([b[5], b[6]]),
            uid: rd32(b, 7),
            gid: rd32(b, 11),
            size: rd64(b, 15),
            atime: rd64(b, 23) as i64,
            mtime: rd64(b, 31) as i64,
            ctime: rd64(b, 39) as i64,
            nlink: rd32(b, 47),
        }
    }

    fn store(&self, b: &mut [u8]) {
        b[4] = self.kind;
        b[5..7].copy_from_slice(&self.mode.to_le_bytes());
        b[7..11].copy_from_slice(&self.uid.to_le_bytes());
        b[11..15].copy_from_slice(&self.gid.to_le_bytes());
        b[15..23].copy_from_slice(&self.size.to_le_bytes());
        b[23..31].copy_from_slice(&self.atime.to_le_bytes());
        b[31..39].copy_from_slice(&self.mtime.to_le_bytes());
        b[39..47].copy_from_slice(&self.ctime.to_le_bytes());
        b[47..51].copy_from_slice(&self.nlink.to_le_bytes());
    }
}

/// Number of inodes needed to hold `len` bytes of file data.
fn needed(len: usize) -> usize {
    if len <= ISZ - HEAD {
        1
    } else {
        1 + (len - (ISZ - HEAD)).div_ceil(ISZ - CONT)
    }
}

struct Disk {
    f: File,
    n: u32,
    bitmap: Vec<u8>,
}

impl Disk {
    fn open(path: &str) -> io::Result<Disk> {
        let f = OpenOptions::new().read(true).write(true).open(path)?;
        let n = (f.metadata()?.len() / (ISZ as u64 + 1)) as u32;
        let mut bitmap = vec![0; n as usize];
        f.read_exact_at(&mut bitmap, 0)?;
        Ok(Disk { f, n, bitmap })
    }

    fn off(&self, i: u32) -> u64 {
        self.n as u64 + i as u64 * ISZ as u64
    }

    fn get(&self, i: u32) -> Vec<u8> {
        let mut b = vec![0; ISZ];
        self.f.read_exact_at(&mut b, self.off(i)).expect("read inode");
        b
    }

    fn put(&self, i: u32, b: &[u8]) {
        self.f.write_all_at(b, self.off(i)).expect("write inode");
    }

    fn mark(&mut self, i: u32, used: bool) {
        self.bitmap[i as usize] = used as u8;
        self.f.write_all_at(&[used as u8], i as u64).expect("write inode list");
    }

    fn free_count(&self) -> usize {
        self.bitmap.iter().filter(|&&b| b == 0).count()
    }

    fn alloc(&mut self) -> Res<u32> {
        let i = self.bitmap.iter().position(|&b| b == 0).ok_or(libc::ENOSPC)? as u32;
        self.mark(i, true);
        Ok(i)
    }

    fn stat(&self, i: u32) -> Res<Stat> {
        if i >= self.n || self.bitmap[i as usize] == 0 {
            return Err(libc::ENOENT);
        }
        let s = Stat::parse(&self.get(i));
        if s.kind != T_FILE && s.kind != T_DIR {
            return Err(libc::EIO);
        }
        Ok(s)
    }

    fn set_stat(&self, i: u32, s: &Stat) {
        let mut b = self.get(i);
        s.store(&mut b);
        self.put(i, &b);
    }

    fn chain(&self, i: u32) -> Vec<u32> {
        let mut v = vec![i];
        loop {
            let nx = rd32(&self.get(*v.last().unwrap()), 0);
            if nx == 0 || nx >= self.n || v.len() > self.n as usize {
                return v;
            }
            v.push(nx);
        }
    }

    fn read_data(&self, i: u32) -> Res<Vec<u8>> {
        let size = self.stat(i)?.size as usize;
        let mut out = Vec::with_capacity(size);
        let mut cur = i;
        let mut hdr = HEAD;
        while out.len() < size {
            let b = self.get(cur);
            let take = (ISZ - hdr).min(size - out.len());
            out.extend_from_slice(&b[hdr..hdr + take]);
            hdr = CONT;
            cur = rd32(&b, 0);
            if cur == 0 || cur >= self.n {
                break;
            }
        }
        Ok(out)
    }

    /// Replace the whole content of file `i`, growing or shrinking its chain.
    /// Freed inodes are only marked free in the inode list, never wiped.
    fn write_data(&mut self, i: u32, data: &[u8]) -> Res<()> {
        let mut chain = self.chain(i);
        let need = needed(data.len());
        if need > chain.len() {
            if need - chain.len() > self.free_count() {
                return Err(libc::ENOSPC);
            }
            while chain.len() < need {
                chain.push(self.alloc()?);
            }
        } else {
            for &x in &chain[need..] {
                self.mark(x, false);
            }
            chain.truncate(need);
        }
        let mut pos = 0;
        for (k, &x) in chain.iter().enumerate() {
            let mut b = self.get(x);
            let hdr = if k == 0 { HEAD } else { CONT };
            if k > 0 {
                b[4] = T_CONT;
            }
            let nx = chain.get(k + 1).copied().unwrap_or(0);
            b[0..4].copy_from_slice(&nx.to_le_bytes());
            let take = (ISZ - hdr).min(data.len() - pos);
            b[hdr..hdr + take].copy_from_slice(&data[pos..pos + take]);
            pos += take;
            if k == 0 {
                let mut s = Stat::parse(&b);
                s.size = data.len() as u64;
                s.mtime = now();
                s.ctime = s.mtime;
                s.store(&mut b);
            }
            self.put(x, &b);
        }
        Ok(())
    }

    fn read_dir(&self, i: u32) -> Res<Vec<(Vec<u8>, u32)>> {
        if self.stat(i)?.kind != T_DIR {
            return Err(libc::ENOTDIR);
        }
        let data = self.read_data(i)?;
        let mut ents = Vec::new();
        let mut p = 0;
        while p + 5 <= data.len() {
            let ino = rd32(&data, p);
            let len = data[p + 4] as usize;
            if p + 5 + len > data.len() {
                break;
            }
            ents.push((data[p + 5..p + 5 + len].to_vec(), ino));
            p += 5 + len;
        }
        Ok(ents)
    }

    fn write_dir(&mut self, i: u32, ents: &[(Vec<u8>, u32)]) -> Res<()> {
        let mut data = Vec::new();
        for (name, ino) in ents {
            data.extend_from_slice(&ino.to_le_bytes());
            data.push(name.len() as u8);
            data.extend_from_slice(name);
        }
        self.write_data(i, &data)
    }

    fn lookup(&self, parent: u32, name: &[u8]) -> Res<u32> {
        self.read_dir(parent)?
            .into_iter()
            .find(|(n, _)| n == name)
            .map(|(_, i)| i)
            .ok_or(libc::ENOENT)
    }

    fn new_node(&mut self, kind: u8, mode: u16, uid: u32, gid: u32) -> Res<u32> {
        let i = self.alloc()?;
        let mut b = self.get(i);
        b[0..4].copy_from_slice(&0u32.to_le_bytes());
        let t = now();
        Stat {
            kind,
            mode,
            uid,
            gid,
            size: 0,
            atime: t,
            mtime: t,
            ctime: t,
            nlink: if kind == T_DIR { 2 } else { 1 },
        }
        .store(&mut b);
        self.put(i, &b);
        Ok(i)
    }

    fn free_node(&mut self, i: u32) {
        for x in self.chain(i) {
            self.mark(x, false);
        }
    }

    fn adjust_nlink(&mut self, i: u32, delta: i32) -> Res<()> {
        let mut s = self.stat(i)?;
        s.nlink = (s.nlink as i32 + delta).max(0) as u32;
        self.set_stat(i, &s);
        Ok(())
    }
}

struct MyFs {
    d: Disk,
}

fn idx(ino: u64) -> u32 {
    (ino - 1) as u32
}

macro_rules! tri {
    ($e:expr, $r:expr) => {
        match $e {
            Ok(v) => v,
            Err(e) => {
                $r.error(e);
                return;
            }
        }
    };
}

impl MyFs {
    fn attr(&self, i: u32) -> Res<FileAttr> {
        let s = self.d.stat(i)?;
        let blocks = needed(s.size as usize) as u64;
        Ok(FileAttr {
            ino: i as u64 + 1,
            size: s.size,
            blocks: (blocks * ISZ as u64).div_ceil(512),
            atime: to_time(s.atime),
            mtime: to_time(s.mtime),
            ctime: to_time(s.ctime),
            crtime: to_time(s.ctime),
            kind: if s.kind == T_DIR { FileType::Directory } else { FileType::RegularFile },
            perm: s.mode & 0o7777,
            nlink: s.nlink,
            uid: s.uid,
            gid: s.gid,
            rdev: 0,
            blksize: 4096,
            flags: 0,
        })
    }

    fn make(&mut self, req: &Request, parent: u32, name: &[u8], kind: u8, mode: u32) -> Res<u32> {
        if name.len() > 255 {
            return Err(libc::ENAMETOOLONG);
        }
        let mut ents = self.d.read_dir(parent)?;
        if ents.iter().any(|(n, _)| n == name) {
            return Err(libc::EEXIST);
        }
        let i = self.d.new_node(kind, (mode & 0o7777) as u16, req.uid(), req.gid())?;
        ents.push((name.to_vec(), i));
        if let Err(e) = self.d.write_dir(parent, &ents) {
            self.d.free_node(i);
            return Err(e);
        }
        if kind == T_DIR {
            self.d.adjust_nlink(parent, 1)?;
        }
        Ok(i)
    }

    fn remove(&mut self, parent: u32, name: &[u8], want_dir: bool) -> Res<()> {
        let mut ents = self.d.read_dir(parent)?;
        let pos = ents.iter().position(|(n, _)| n == name).ok_or(libc::ENOENT)?;
        let i = ents[pos].1;
        let is_dir = self.d.stat(i)?.kind == T_DIR;
        if want_dir && !is_dir {
            return Err(libc::ENOTDIR);
        }
        if !want_dir && is_dir {
            return Err(libc::EISDIR);
        }
        if is_dir && !self.d.read_dir(i)?.is_empty() {
            return Err(libc::ENOTEMPTY);
        }
        ents.remove(pos);
        self.d.write_dir(parent, &ents)?;
        self.d.free_node(i);
        if is_dir {
            self.d.adjust_nlink(parent, -1)?;
        }
        Ok(())
    }

    fn do_rename(&mut self, parent: u32, name: &[u8], newparent: u32, newname: &[u8], flags: u32) -> Res<()> {
        if newname.len() > 255 {
            return Err(libc::ENAMETOOLONG);
        }
        let src = self.d.lookup(parent, name)?;
        let src_dir = self.d.stat(src)?.kind == T_DIR;
        if let Ok(dst) = self.d.lookup(newparent, newname) {
            if flags & libc::RENAME_NOREPLACE != 0 {
                return Err(libc::EEXIST);
            }
            if dst == src {
                return Ok(());
            }
            self.remove(newparent, newname, self.d.stat(dst)?.kind == T_DIR)?;
        }
        let mut ents = self.d.read_dir(parent)?;
        ents.retain(|(n, _)| n != name);
        if parent == newparent {
            ents.push((newname.to_vec(), src));
            return self.d.write_dir(parent, &ents);
        }
        self.d.write_dir(parent, &ents)?;
        let mut nents = self.d.read_dir(newparent)?;
        nents.push((newname.to_vec(), src));
        self.d.write_dir(newparent, &nents)?;
        if src_dir {
            self.d.adjust_nlink(parent, -1)?;
            self.d.adjust_nlink(newparent, 1)?;
        }
        Ok(())
    }
}

impl Filesystem for MyFs {
    fn lookup(&mut self, _req: &Request, parent: u64, name: &OsStr, reply: ReplyEntry) {
        let i = tri!(self.d.lookup(idx(parent), name.as_bytes()), reply);
        let a = tri!(self.attr(i), reply);
        reply.entry(&TTL, &a, 0);
    }

    fn getattr(&mut self, _req: &Request, ino: u64, _fh: Option<u64>, reply: ReplyAttr) {
        let a = tri!(self.attr(idx(ino)), reply);
        reply.attr(&TTL, &a);
    }

    fn setattr(
        &mut self,
        _req: &Request,
        ino: u64,
        mode: Option<u32>,
        uid: Option<u32>,
        gid: Option<u32>,
        size: Option<u64>,
        atime: Option<TimeOrNow>,
        mtime: Option<TimeOrNow>,
        _ctime: Option<SystemTime>,
        _fh: Option<u64>,
        _crtime: Option<SystemTime>,
        _chgtime: Option<SystemTime>,
        _bkuptime: Option<SystemTime>,
        _flags: Option<u32>,
        reply: ReplyAttr,
    ) {
        let i = idx(ino);
        if let Some(size) = size {
            let mut data = tri!(self.d.read_data(i), reply);
            data.resize(size as usize, 0);
            tri!(self.d.write_data(i, &data), reply);
        }
        let mut s = tri!(self.d.stat(i), reply);
        if let Some(m) = mode {
            s.mode = (m & 0o7777) as u16;
        }
        if let Some(u) = uid {
            s.uid = u;
        }
        if let Some(g) = gid {
            s.gid = g;
        }
        if let Some(t) = atime {
            s.atime = from_time(t);
        }
        if let Some(t) = mtime {
            s.mtime = from_time(t);
        }
        s.ctime = now();
        self.d.set_stat(i, &s);
        let a = tri!(self.attr(i), reply);
        reply.attr(&TTL, &a);
    }

    fn mknod(&mut self, req: &Request, parent: u64, name: &OsStr, mode: u32, umask: u32, _rdev: u32, reply: ReplyEntry) {
        if mode & libc::S_IFMT != libc::S_IFREG {
            reply.error(libc::EPERM);
            return;
        }
        let i = tri!(self.make(req, idx(parent), name.as_bytes(), T_FILE, mode & !umask), reply);
        let a = tri!(self.attr(i), reply);
        reply.entry(&TTL, &a, 0);
    }

    fn mkdir(&mut self, req: &Request, parent: u64, name: &OsStr, mode: u32, umask: u32, reply: ReplyEntry) {
        let i = tri!(self.make(req, idx(parent), name.as_bytes(), T_DIR, mode & !umask), reply);
        let a = tri!(self.attr(i), reply);
        reply.entry(&TTL, &a, 0);
    }

    fn create(
        &mut self,
        req: &Request,
        parent: u64,
        name: &OsStr,
        mode: u32,
        umask: u32,
        _flags: i32,
        reply: ReplyCreate,
    ) {
        let i = tri!(self.make(req, idx(parent), name.as_bytes(), T_FILE, mode & !umask), reply);
        let a = tri!(self.attr(i), reply);
        reply.created(&TTL, &a, 0, 0, 0);
    }

    fn unlink(&mut self, _req: &Request, parent: u64, name: &OsStr, reply: ReplyEmpty) {
        tri!(self.remove(idx(parent), name.as_bytes(), false), reply);
        reply.ok();
    }

    fn rmdir(&mut self, _req: &Request, parent: u64, name: &OsStr, reply: ReplyEmpty) {
        tri!(self.remove(idx(parent), name.as_bytes(), true), reply);
        reply.ok();
    }

    fn rename(
        &mut self,
        _req: &Request,
        parent: u64,
        name: &OsStr,
        newparent: u64,
        newname: &OsStr,
        flags: u32,
        reply: ReplyEmpty,
    ) {
        tri!(self.do_rename(idx(parent), name.as_bytes(), idx(newparent), newname.as_bytes(), flags), reply);
        reply.ok();
    }

    fn read(
        &mut self,
        _req: &Request,
        ino: u64,
        _fh: u64,
        offset: i64,
        size: u32,
        _flags: i32,
        _lock_owner: Option<u64>,
        reply: ReplyData,
    ) {
        let data = tri!(self.d.read_data(idx(ino)), reply);
        let start = (offset as usize).min(data.len());
        let end = (start + size as usize).min(data.len());
        reply.data(&data[start..end]);
    }

    fn write(
        &mut self,
        _req: &Request,
        ino: u64,
        _fh: u64,
        offset: i64,
        buf: &[u8],
        _write_flags: u32,
        _flags: i32,
        _lock_owner: Option<u64>,
        reply: ReplyWrite,
    ) {
        let i = idx(ino);
        let mut data = tri!(self.d.read_data(i), reply);
        let end = offset as usize + buf.len();
        if data.len() < end {
            data.resize(end, 0);
        }
        data[offset as usize..end].copy_from_slice(buf);
        tri!(self.d.write_data(i, &data), reply);
        reply.written(buf.len() as u32);
    }

    fn readdir(&mut self, _req: &Request, ino: u64, _fh: u64, offset: i64, mut reply: ReplyDirectory) {
        let ents = tri!(self.d.read_dir(idx(ino)), reply);
        let mut all = vec![
            (ino, FileType::Directory, b".".to_vec()),
            (ino, FileType::Directory, b"..".to_vec()),
        ];
        for (name, i) in ents {
            let kind = match self.d.stat(i) {
                Ok(s) if s.kind == T_DIR => FileType::Directory,
                _ => FileType::RegularFile,
            };
            all.push((i as u64 + 1, kind, name));
        }
        for (k, (i, kind, name)) in all.into_iter().enumerate().skip(offset as usize) {
            if reply.add(i, k as i64 + 1, kind, OsStr::from_bytes(&name)) {
                break;
            }
        }
        reply.ok();
    }

    fn statfs(&mut self, _req: &Request, _ino: u64, reply: ReplyStatfs) {
        let free = self.d.free_count() as u64;
        reply.statfs(self.d.n as u64, free, free, self.d.n as u64, free, ISZ as u32, 255, ISZ as u32);
    }
}

fn mkfs(path: &str, size: u64) -> io::Result<()> {
    let n = (size / (ISZ as u64 + 1)) as u32;
    if n < 1 {
        return Err(io::Error::other("device too small"));
    }
    let f = OpenOptions::new().read(true).write(true).create(true).truncate(true).open(path)?;
    f.set_len(size)?;
    drop(f);
    let mut d = Disk::open(path)?;
    d.mark(0, true);
    let mut b = vec![0; ISZ];
    let t = now();
    Stat {
        kind: T_DIR,
        mode: 0o755,
        uid: unsafe { libc::getuid() },
        gid: unsafe { libc::getgid() },
        size: 0,
        atime: t,
        mtime: t,
        ctime: t,
        nlink: 2,
    }
    .store(&mut b);
    d.put(0, &b);
    println!("{path}: {n} inodes of {ISZ} bytes");
    Ok(())
}

/// Randomly permute the physical positions of inodes 1..N, rewriting every
/// next pointer and directory entry so the filesystem stays consistent.
fn shuffle(path: &str, seed: [u8; 32]) -> io::Result<()> {
    let mut rng = ChaCha20Rng::from_seed(seed);
    let mut d = Disk::open(path)?;
    let n = d.n as usize;
    let mut p: Vec<u32> = (0..n as u32).collect();
    p[1..].shuffle(&mut rng);

    for i in 0..n as u32 {
        if d.bitmap[i as usize] == 0 || d.get(i)[4] != T_DIR {
            continue;
        }
        let s = d.stat(i).unwrap();
        let ents: Vec<_> = d.read_dir(i).unwrap().into_iter().map(|(name, x)| (name, p[x as usize])).collect();
        d.write_dir(i, &ents).unwrap();
        d.set_stat(i, &s);
    }

    let mut inodes = vec![Vec::new(); n];
    let mut bitmap = vec![0u8; n];
    for i in 0..n {
        let mut b = d.get(i as u32);
        let nx = rd32(&b, 0) as usize;
        if nx != 0 && nx < n {
            b[0..4].copy_from_slice(&p[nx].to_le_bytes());
        }
        inodes[p[i] as usize] = b;
        bitmap[p[i] as usize] = d.bitmap[i];
    }
    for (i, b) in inodes.iter().enumerate() {
        d.put(i as u32, b);
    }
    d.f.write_all_at(&bitmap, 0)?;
    Ok(())
}

fn usage() -> ! {
    eprintln!("usage:\n  myfs mkfs <image> <size>\n  myfs mount <image> <mountpoint>\n  myfs shuffle <image> [seed-string]");
    std::process::exit(1);
}

fn main() -> io::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("mkfs") if args.len() == 4 => mkfs(&args[2], args[3].parse().unwrap_or_else(|_| usage())),
        Some("mount") if args.len() == 4 => {
            let fs = MyFs { d: Disk::open(&args[2])? };
            fuser::mount2(fs, &args[3], &[MountOption::FSName("myfs".into()), MountOption::Subtype("myfs".into())])
        }
        Some("shuffle") if args.len() == 3 || args.len() == 4 => {
            // An explicit seed may be any string; it is hashed into a 256-bit ChaCha20 key.
            // Without one, the key comes from the OS CSPRNG and is printed for reproducibility.
            let seed: [u8; 32] = match args.get(3) {
                Some(s) => Sha256::digest(s.as_bytes()).into(),
                None => {
                    let mut k = [0; 32];
                    getrandom::fill(&mut k).map_err(io::Error::other)?;
                    let hex: String = k.iter().map(|b| format!("{b:02x}")).collect();
                    println!("shuffle seed key: {hex}");
                    k
                }
            };
            shuffle(&args[2], seed)
        }
        _ => usage(),
    }
}
