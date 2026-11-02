"""Carving helpers for Burnt Note evidence.

Recovers `messages` rows from:
  * raw page images of a main database file (live pages, freelist pages,
    remnants inside in-page freeblocks),
  * WAL frames (regardless of the WAL header state).

Row layout is fixed by the task schema:

    CREATE TABLE messages(
      id INTEGER PRIMARY KEY,     -- NULL in record, aliased to rowid
      created_at INTEGER,         -- unix ms, 6-byte int (serial type 5)
      sender TEXT,                -- exactly 1 char  -> serial type 0x0F
      nonce BLOB,                 -- exactly 12 B    -> serial type 0x24
      frame BLOB                  -- exactly 1416 B  -> serial type 2844 (2-byte varint 0x96 0x1C)
    );

Record serial-type tail is therefore the 6-byte signature
    00 05 0f 24 96 1c
followed by the 1435-byte body. A deleted-in-place cell loses its first
four bytes (payload len + rowid varints + record header-length byte) to the
freeblock header, so the scan starts at the serial-type tail, not at the
record start. rowid is then recovered heuristically from the preceding
varints when they are intact; otherwise rows are ranked by created_at
(ids and created_at are strictly co-monotonic in this task).
"""

import re

PAGE_SIZE = 4096
BODY_LEN = 6 + 1 + 12 + 1416  # created_at + sender + nonce + frame
RECORD_TAIL = b"\x00\x05\x0f\x24\x96\x1c"  # serial types, see module docstring
WAL_HEADER = 32
WAL_FRAME_HEADER = 24


def _varint(data, off):
    val = 0
    for i in range(9):
        b = data[off + i]
        if i == 8:
            val = (val << 8) | b
            return val, off + 9
        val = (val << 7) | (b & 0x7F)
        if not b & 0x80:
            return val, off + i + 1


class Row:
    __slots__ = ("rowid", "created_at", "sender", "nonce", "frame")

    def __init__(self, rowid, created_at, sender, nonce, frame):
        self.rowid = rowid
        self.created_at = created_at
        self.sender = sender
        self.nonce = nonce
        self.frame = frame

    def body_span(self, off_tail):
        return off_tail + len(RECORD_TAIL), off_tail + len(RECORD_TAIL) + BODY_LEN


def _parse_rows(data, allow_rowid_backscan=True):
    rows = []
    for m in re.finditer(re.escape(RECORD_TAIL), data):
        off = m.end()
        body = data[off:off + BODY_LEN]
        if len(body) != BODY_LEN:
            continue
        created_at = int.from_bytes(body[:6], "big", signed=False)
        # top two bits must be zero for values that fit 6 bytes
        if created_at >> 48:
            continue
        sender = chr(body[6])
        if sender not in "CR":
            continue
        nonce = bytes(body[7:19])
        frame = bytes(body[19:])
        rowid = None
        if allow_rowid_backscan:
            # live cell: [payload_varint][rowid_varint][record...]; record
            # starts one byte (header len) before the signature.
            for back in (3, 4, 5):
                start = m.start() - back
                if start < 0:
                    continue
                try:
                    plen, pos = _varint(data, start)
                    rid, _ = _varint(data, pos)
                except IndexError:
                    continue
                if plen == 1 + len(RECORD_TAIL) + BODY_LEN and 0 < rid < 1 << 31:
                    rowid = rid
                    break
        rows.append(Row(rowid, created_at, sender, nonce, frame))
    return rows


def carve_db(data):
    """Carve rows from a main database file image (any page state)."""
    return _parse_rows(data)


def carve_wal(data):
    """Carve rows from every frame of a WAL file, ignoring its header."""
    rows = []
    off = WAL_HEADER
    idx = 0
    while off + WAL_FRAME_HEADER + PAGE_SIZE <= len(data):
        page_no = int.from_bytes(data[off:off + 4], "big")
        commit = int.from_bytes(data[off + 4:off + 8], "big")
        if page_no == 0:
            break  # past the written frames
        page = data[off + WAL_FRAME_HEADER:
                    off + WAL_FRAME_HEADER + PAGE_SIZE]
        rows.extend(_parse_rows(page))
        off += WAL_FRAME_HEADER + PAGE_SIZE
        idx += 1
    return rows


def dedupe_by_time(rows):
    """Drop duplicate row images, keeping any with an explicit rowid."""
    best = {}
    for r in rows:
        cur = best.get(r.created_at)
        if cur is None or (cur.rowid is None and r.rowid is not None):
            best[r.created_at] = r
    out = sorted(best.values(), key=lambda r: r.created_at)
    for i, r in enumerate(out, 1):
        if r.rowid is None:
            r.rowid = i
    return out


def collect_candidates(rows):
    """Group row images by message id.

    Carving often finds several physical images of the same logical row
    (live cells, stale page copies, WAL frames). Some images are damaged
    where SQLite structures overwrote a few bytes (e.g. an interior cell
    replacing a stale leaf's tail), so keep every candidate and let the
    caller pick the one that authenticates under GCM.
    """
    by_ts = {}
    for r in rows:
        by_ts.setdefault(r.created_at, []).append(r)
    ids = {ts: i + 1 for i, ts in enumerate(sorted(by_ts))}
    out = {}
    for ts, group in by_ts.items():
        rid = ids[ts]
        for r in group:
            r.rowid = rid
        out[rid] = group
    return out
