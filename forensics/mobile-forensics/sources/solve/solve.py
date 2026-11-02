#!/usr/bin/env python3
"""Author's solver for Burnt Note (Hard++ mobile forensics).

Walks the full intended solution path:

  1. parse four seed-fragment artifacts in four timestamp formats,
  2. normalize all timestamps to UTC and order the fragments,
  3. read ANDROID_ID from settings_secure.xml (PBKDF2 salt),
  4. carve message rows from the raw main DB pages and the WAL frames,
  5. walk the ratchet chain, authenticating each row image via GCM,

and prints the recovered conversation plus the flag.

Stdlib only (pure-python AES-256-GCM lives in tools/aesgcm.py).

Usage: python3 solve.py [evidence.tar.gz]
"""

import hashlib
import hmac
import io
import json
import re
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import aesgcm  # noqa: E402
import sqlcarve  # noqa: E402

PAD_LEN = 1400
PBKDF2_ITERS = 100_000
WEBKIT_DELTA = 11_644_473_600

PATH_MAIN = "data/data/com.ctf.burntnote/databases/messages.db"
PATH_WAL = "data/data/com.ctf.burntnote/databases/messages.db-wal"
PATH_LOG = "data/data/com.ctf.burntnote/files/diagnostics.log"
PATH_SECURE = "data/secure/0/settings_secure.xml"
PATH_CHROME = "data/data/com.android.chrome/app_chrome/Default/History"
PATH_MSGSTORE = "data/data/com.whatsapp/databases/msgstore.db"
PATH_JPEG = "sdcard/DCIM/Camera/IMG_20260113_192401.jpg"


# ---------------------------------------------------------------------------
# seed fragments, one per artifact, each with its native time format
# ---------------------------------------------------------------------------

def fragment_whatsapp(data: bytes):
    """msgstore.db: timestamp is UNIX SECONDS."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        con = sqlite3.connect(tmp.name)
        rows = con.execute(
            "SELECT timestamp, text_data FROM messages ORDER BY timestamp"
        ).fetchall()
        con.close()
    for ts, text in rows:
        if not text:
            continue
        m = re.search(r"([0-9a-f]{12})", text)
        if m and "Burnt" in text:
            utc = datetime.fromtimestamp(ts, timezone.utc)
            return "whatsapp_msgstore_unix_sec", m.group(1), utc
    raise LookupError("whatsapp fragment not found")


def fragment_chrome(data: bytes):
    """Chrome History: visit_time is WebKit microseconds since 1601-01-01."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        con = sqlite3.connect(tmp.name)
        rows = con.execute(
            "SELECT u.url, v.visit_time FROM visits v "
            "JOIN urls u ON u.id = v.url ORDER BY v.visit_time").fetchall()
        con.close()
    for url, wk in rows:
        m = re.search(r"paste\.burntnote\.onion/k/([0-9a-f]{12})", url)
        if m:
            epoch_s = wk / 1_000_000 - WEBKIT_DELTA
            return "chrome_history_webkit_us", m.group(1), \
                datetime.fromtimestamp(epoch_s, timezone.utc)
    raise LookupError("chrome fragment not found")


def fragment_log(data: bytes):
    """diagnostics.log: bracketed UNIX MILLISECONDS."""
    for line in data.decode().splitlines():
        m = re.match(r"^\[(\d{13})\] seed fragment captured "
                     r"\(device entropy\): ([0-9a-f]{12})$", line)
        if m:
            utc = datetime.fromtimestamp(int(m.group(1)) / 1000, timezone.utc)
            return "diagnostics_log_unix_ms", m.group(2), utc
    raise LookupError("log fragment not found")


def fragment_exif(data: bytes):
    """JPEG EXIF: DateTimeOriginal is LOCAL time, offset in OffsetTime."""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    ex = img.getexif()
    dt = ex[0x9003]                       # "2026:01:13 19:24:01"
    off = ex.get(0x9010) or "+03:00"      # OffsetTime
    comment = ex[0x9286]                  # b"ASCII\0\0\0" + hex
    local = datetime.strptime(dt, "%Y:%m:%d %H:%M:%S")
    sign = 1 if off[0] == "+" else -1
    delta = timedelta(hours=int(off[1:3]), minutes=int(off[4:6]))
    utc = local - sign * delta
    frag = re.search(r"([0-9a-f]{12})$", comment.decode("ascii")).group(1)
    return "photo_exif_local_offset", frag, utc.replace(tzinfo=timezone.utc)


def read_android_id(data: bytes) -> str:
    m = re.search(rb'name="android_id" value="([0-9a-f]{16})"', data)
    if not m:
        raise LookupError("android_id not found")
    return m.group(1).decode()


# ---------------------------------------------------------------------------
# chain walk
# ---------------------------------------------------------------------------

def decrypt_chain(candidates, seed_string, android_id, n=12):
    master = hashlib.pbkdf2_hmac(
        "sha256", seed_string.encode(), android_id.encode(), PBKDF2_ITERS, 32)
    out = []
    prev_key, prev_plain = None, None
    for i in range(1, n + 1):
        if i == 1:
            key = hmac.new(master, b"burnt-note/root", hashlib.sha256).digest()
        else:
            key = hmac.new(
                prev_key,
                prev_plain + f"|burnt-note/step|{i}".encode(),
                hashlib.sha256).digest()
        aad = f"burnt-note/msg/{i}".encode()
        chosen = None
        for cand in candidates.get(i, []):
            try:
                pt = aesgcm.gcm_decrypt(key, cand.nonce, aad, cand.frame)
            except ValueError:
                continue  # damaged image: GCM tag rejects it
            chosen = (cand, pt)
            break
        if chosen is None:
            raise ValueError(
                f"message {i}: no authentic image among "
                f"{len(candidates.get(i, []))} candidates")
        cand, pt = chosen
        prev_key, prev_plain = key, pt
        out.append((i, cand.sender, cand.created_at, pt))
    return out


def solve_archive(archive_bytes: bytes):
    members = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile():
                members[m.name.lstrip("/")] = tf.extractfile(m).read()

    frags = [
        fragment_whatsapp(members[PATH_MSGSTORE]),
        fragment_chrome(members[PATH_CHROME]),
        fragment_log(members[PATH_LOG]),
        fragment_exif(members[PATH_JPEG]),
    ]
    frags.sort(key=lambda t: t[2])
    seed_string = "-".join(f for _, f, _ in frags)
    android_id = read_android_id(members[PATH_SECURE])

    rows = (sqlcarve.carve_db(members[PATH_MAIN])
            + sqlcarve.carve_wal(members[PATH_WAL]))
    candidates = sqlcarve.collect_candidates(rows)

    msgs = decrypt_chain(candidates, seed_string, android_id)

    result = {
        "fragments": [
            {"source": src, "fragment": frag, "utc": utc.isoformat()}
            for src, frag, utc in frags],
        "seed_string": seed_string,
        "android_id": android_id,
        "messages": [],
        "flag": None,
    }
    for i, sender, created_at, padded in msgs:
        text = padded.rstrip(b"\x00").decode("utf-8")
        result["messages"].append({
            "id": i, "sender": sender,
            "created_at_utc": datetime.fromtimestamp(
                created_at / 1000, timezone.utc).isoformat(),
            "text": text,
        })
        m = re.search(r"ctfcup\{[^}]*\}", text)
        if m:
            result["flag"] = m.group(0)
    return result


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        str(Path(__file__).resolve().parent.parent / "handout/evidence.tar.gz")
    res = solve_archive(Path(path).read_bytes())
    print(json.dumps(res["fragments"], indent=2, ensure_ascii=False))
    print("seed :", res["seed_string"])
    print("salt :", res["android_id"])
    print("-" * 72)
    who = {"C": "Курьер ", "R": "Приёмщик"}
    for m in res["messages"]:
        ts = m["created_at_utc"][11:19]
        print(f'[{m["id"]:2}] {ts} {who[m["sender"]]}: {m["text"]}')
    print("-" * 72)
    print("FLAG:", res["flag"])
    return 0 if res["flag"] else 1


if __name__ == "__main__":
    sys.exit(main())
