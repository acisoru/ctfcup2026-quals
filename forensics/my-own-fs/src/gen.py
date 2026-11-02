#!/usr/bin/env python3
"""Build public/disk.img: populate a myfs image through FUSE, shuffle inodes, delete all root dirs."""

import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FLAG = "ctfcup{dbf75e112fef01db44b2a0e68ab2065e}"
IMG_SIZE = 4 * 1024 * 1024
FONT = "/usr/share/fonts/liberation/LiberationMono-Bold.ttf"

ROOT = Path(__file__).resolve().parent.parent
CRATE = ROOT / "src" / "myfs"
BIN = CRATE / "target" / "release" / "myfs"
OUT = ROOT / "public" / "my-own-fs.zip"
SOURCES = ["Cargo.toml", "Cargo.lock", "src/main.rs"]

WORDS = (
    "alpha bravo backup cache config data docs drafts etc home logs media misc notes old "
    "photos projects reports scripts share src stuff temp tmp work archive build cfg lib "
    "var srv users vacation recipes invoices music games keys db dumps export import"
).split()
LOREM = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt "
    "ut labore et dolore magna aliqua enim ad minim veniam quis nostrud exercitation ullamco "
    "laboris nisi aliquip ex ea commodo consequat duis aute irure in reprehenderit voluptate"
).split()

rng = random.SystemRandom()


def make_flag_png(path):
    w, h = 900, 160
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            n = rng.randrange(40)
            px[x, y] = (20 + n, 24 + (x * 60 // w) + n, 40 + (y * 80 // h) + n)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 34)
    d.text((w // 2, h // 2), FLAG, font=font, fill=(240, 220, 90), anchor="mm")
    img.save(path, "PNG")


def random_file_content(ext):
    if ext in (".bin", ".dat"):
        return rng.randbytes(rng.randrange(64, 3000))
    if ext == ".json":
        items = ", ".join(f'"{rng.choice(LOREM)}": {rng.randrange(10**6)}' for _ in range(rng.randrange(3, 40)))
        return ("{" + items + "}\n").encode()
    if ext == ".log":
        lines = [
            f"2026-10-{rng.randrange(1, 31):02d} {rng.randrange(24):02d}:{rng.randrange(60):02d} "
            f"[{rng.choice(['INFO', 'WARN', 'DEBUG', 'ERROR'])}] {' '.join(rng.choices(LOREM, k=rng.randrange(3, 10)))}"
            for _ in range(rng.randrange(2, 40))
        ]
        return ("\n".join(lines) + "\n").encode()
    return (" ".join(rng.choices(LOREM, k=rng.randrange(10, 400))) + "\n").encode()


def populate(mnt, png):
    dirs = []

    def build(path, depth):
        for _ in range(rng.randrange(2, 6)):
            ext = rng.choice([".txt", ".log", ".json", ".bin", ".dat", ".md", ".cfg"])
            name = f"{rng.choice(WORDS)}_{rng.randrange(1000)}{ext}"
            (path / name).write_bytes(random_file_content(ext))
        if depth >= 6:
            return
        for name in rng.sample(WORDS, rng.randrange(1 if depth < 3 else 0, 4)):
            sub = path / name
            sub.mkdir()
            dirs.append((sub, depth + 1))
            build(sub, depth + 1)

    for name in rng.sample(WORDS, 3):
        (mnt / name).mkdir()
        dirs.append((mnt / name, 1))
        build(mnt / name, 1)

    deep = [d for d, depth in dirs if depth >= 5]
    target = rng.choice(deep)
    shutil.copyfile(png, target / "flag.png")
    print("flag.png at", target.relative_to(mnt))

    (mnt / "README.txt").write_text("nothing to see here, everything was cleaned up\n")
    (mnt / "todo.txt").write_text("- wipe old backups\n- buy milk\n")


def mounted(img, mnt):
    class M:
        def __enter__(self):
            self.p = subprocess.Popen([BIN, "mount", img, mnt])
            for _ in range(100):
                if os.path.ismount(mnt):
                    return
                time.sleep(0.05)
            sys.exit("mount failed")

        def __exit__(self, *a):
            subprocess.run(["fusermount3", "-u", mnt], check=True)
            self.p.wait()

    return M()


def write_archive(img):
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(img, "my-own-fs/disk.img")
        for f in SOURCES:
            z.write(CRATE / f, f"my-own-fs/myfs/{f}")


def main():
    subprocess.run(["cargo", "build", "--release", "--manifest-path", CRATE / "Cargo.toml"], check=True)
    OUT.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        png = tmp / "flag.png"
        make_flag_png(png)
        print("flag.png size", png.stat().st_size)
        img, mnt = tmp / "disk.img", tmp / "mnt"
        mnt.mkdir()
        subprocess.run([BIN, "mkfs", img, str(IMG_SIZE)], check=True)

        with mounted(img, mnt):
            populate(mnt, png)
            subprocess.run(["df", "-h", mnt])

        subprocess.run([BIN, "shuffle", img], check=True)

        with mounted(img, mnt):
            assert (mnt / "README.txt").exists()
            for p in mnt.iterdir():
                if p.is_dir():
                    shutil.rmtree(p)
            print("root after cleanup:", sorted(p.name for p in mnt.iterdir()))

        write_archive(img)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
