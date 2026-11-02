#!/usr/bin/env python3
"""Burnt Note evidence generator.

Builds the full handout archive deterministically:
  * messages.db with a three-layer "burned" history,
  * four seed-fragment artifacts in four different timestamp formats,
  * noise artifacts for realism,
then verifies the whole task end-to-end using the same carving + crypto
code paths a player is expected to follow (tools/sqlcarve.py + tools/aesgcm.py).

Usage:
    python3 build_evidence.py                     # default flag
    FLAG='ctfcup{...}' python3 build_evidence.py
"""

import hashlib
import hmac
import io
import json
import os
import random
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aesgcm
import sqlcarve

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
BUILD = TASK / "build"
HANDOUT = TASK / "handout"

DEFAULT_FLAG = "ctfcup{ch41n_0f_4sh3s}"
SEED_LEN_HEX = 12          # 12 hex chars per fragment
PAD_LEN = 1400             # padded plaintext size
PBKDF2_ITERS = 100_000

# ---------------------------------------------------------------------------
# Fixed scenario timeline (all 2026-01-13, times are UTC unless noted)
# ---------------------------------------------------------------------------

DAY = datetime(2026, 1, 13, tzinfo=timezone.utc)
T_WA_SEC = DAY + timedelta(hours=16, minutes=2, seconds=11)      # WhatsApp, unix sec
T_EXIF_LOCAL = DAY + timedelta(hours=19, minutes=24, seconds=1)  # local +03:00
T_EXIF_UTC = T_EXIF_LOCAL - timedelta(hours=3)
T_LOG_MS = DAY + timedelta(hours=16, minutes=31, seconds=2, milliseconds=11)  # unix ms
T_CHROME_WEBKIT = DAY + timedelta(hours=16, minutes=45, seconds=33)           # webkit us

CHAT_START = DAY + timedelta(hours=17, minutes=50)  # messages 1..12, every 47 s
CHAT_STEP_MS = 47_000

WEBKIT_EPOCH_DELTA = 11_644_473_600  # seconds between 1601-01-01 and 1970-01-01

MESSAGES = [
    # (sender, text)
    ("C", "Выхожу на смену. Сегодня по старой схеме?"),
    ("R", "Жду. Первая точка после шести, не светись на камерах у арки."),
    ("C", "Понял. Товар у меня, три закладки как договаривались."),
    ("R", "Адреса прежние. Не пиши сюда больше, чем нужно."),
    ("C", "Принял. Если что — созвон по обычному номеру."),
    ("R", "Тише едешь — дальше будешь. Начинай после темноты."),
    ("C", "Все чисто. Первая закрыта."),
    ("R", "Вторая — двор за школой, у синих гаражей."),
    ("C", "Взял. Там камера на столбе, обошел двором."),
    ("R", "Последняя самая важная. Сделаешь — сожги все переписки."),
    ("C", "Готово. Три из трех. Сейчас все сожгу."),
    ("R", None),  # flag message, filled at build time
]

FLAG_TPL = "Подтверждаю приём. Контрольная фраза: {flag}. Сожги и это."


def pad(text: str) -> bytes:
    raw = text.encode("utf-8")
    assert len(raw) <= PAD_LEN, "message too long"
    return raw.ljust(PAD_LEN, b"\x00")


def derive_keys(seed_string: str, android_id: str, plaintexts_padded):
    """Yield (i, key_i) following the APK's BurntCrypto ratchet."""
    master = hashlib.pbkdf2_hmac(
        "sha256", seed_string.encode(), android_id.encode(), PBKDF2_ITERS, 32)
    keys = []
    prev_key = None
    prev_plain = None
    for i in range(1, len(plaintexts_padded) + 1):
        if i == 1:
            key = hmac.new(master, b"burnt-note/root", hashlib.sha256).digest()
        else:
            msg = prev_plain + f"|burnt-note/step|{i}".encode()
            key = hmac.new(prev_key, msg, hashlib.sha256).digest()
        keys.append(key)
        prev_key, prev_plain = key, plaintexts_padded[i - 1]
    return master, keys


def build_messages_db(path: Path, rows):
    """Create messages.db with the exact burned lifecycle.

    Page math: each row is ~1450 bytes on a 4096-byte page, so exactly two
    rows fit per leaf page. Messages are inserted sequentially, so ids pair
    up on pages (1,2)(3,4)(5,6)(7). The phase-A burn removes ids 2 and 4:
    every page keeps a survivor, no page is freed, and the deleted cells
    survive as in-page freeblocks that the allocator never reuses.
    """
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("PRAGMA page_size=4096")
    cur.execute("PRAGMA auto_vacuum=NONE")
    cur.execute("PRAGMA secure_delete=OFF")

    # Courier's test drafts, dropped during onboarding cleanup. DROP TABLE
    # frees whole pages -> these become the freelist layer.
    cur.execute("""CREATE TABLE drafts(
        id INTEGER PRIMARY KEY,
        created_at INTEGER NOT NULL,
        body TEXT NOT NULL)""")
    t = int((DAY + timedelta(hours=17, minutes=21)).timestamp() * 1000)
    cur.executemany("INSERT INTO drafts VALUES (?,?,?)", [
        (1, t, "тест"),
        (2, t + 9000, "проверка связи"),
        (3, t + 21000, "черновик: точка у гаражей?"),
        (4, t + 65000, "удалить после проверки"),
    ])
    con.commit()

    cur.execute("""
        CREATE TABLE messages(
            id INTEGER PRIMARY KEY,
            created_at INTEGER NOT NULL,
            sender TEXT NOT NULL,
            nonce BLOB NOT NULL,
            frame BLOB NOT NULL
        )""")
    # Phase A: rollback journal. Messages 1..7 inserted, then ids 2 and 4
    # are burned after reading (in-page remnants, pages stay allocated).
    for r in rows[:7]:
        cur.execute("INSERT INTO messages VALUES (?,?,?,?,?)", r)
    con.commit()
    cur.execute("DELETE FROM messages WHERE id IN (2,4)")
    con.commit()
    # Drafts cleanup before the night shift: whole pages go to the freelist.
    cur.execute("DROP TABLE drafts")
    con.commit()
    # Phase B: WAL without checkpoint. Messages 8..12 inserted (reusing a
    # couple of freelist pages is fine now), then the total wipe.
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA wal_autocheckpoint=0")
    for r in rows[7:]:
        cur.execute("INSERT INTO messages VALUES (?,?,?,?,?)", r)
    con.commit()
    cur.execute("DELETE FROM messages")
    con.commit()
    return con


def inject_decoy_candidate(path: Path, row):
    """Place one damaged duplicate row into unused freelist space.

    The timestamp is real, but one ciphertext byte is flipped. The row keeps
    the normal carve signature, so the solver must retain both physical
    images and let GCM authentication choose the valid one.
    """
    row_id, created_at, sender, nonce, frame = row
    damaged = bytearray(frame)
    damaged[0] ^= 1
    payload = (sqlcarve.RECORD_TAIL
               + int(created_at).to_bytes(6, "big")
               + sender.encode("ascii")
               + nonce
               + bytes(damaged))
    data = bytearray(path.read_bytes())
    empty = b"\x00" * len(payload)
    for page_start in range(0, len(data), sqlcarve.PAGE_SIZE):
        page_end = min(page_start + sqlcarve.PAGE_SIZE, len(data))
        pos = data.find(empty, page_start, page_end)
        if pos >= page_start:
            data[pos:pos + len(payload)] = payload
            path.write_bytes(data)
            return
    raise RuntimeError("no freelist space for decoy candidate")


def make_jpeg(path: Path, fragment: str):
    from PIL import Image
    w, h = 1600, 1200
    img = Image.new("RGB", (w, h))
    px = img.load()
    rnd = random.Random(0xBEEF)
    for y in range(h):
        for x in range(0, w, 4):
            c = ((x * 255) // w, (y * 255) // h, ((x + y) * 127) // (w + h))
            for dx in range(4):
                if x + dx < w:
                    n = rnd.randint(-12, 12)
                    px[x + dx, y] = tuple(max(0, min(255, v + n)) for v in c)
    ex = Image.Exif()
    local = T_EXIF_LOCAL.strftime("%Y:%m:%d %H:%M:%S")
    ex[0x0132] = local            # DateTime
    ex[0x9003] = local            # DateTimeOriginal
    ex[0x9004] = local            # DateTimeDigitized
    ex[0x9010] = "+03:00"         # OffsetTime
    ex[0x9011] = "+03:00"         # OffsetTimeOriginal
    ex[0x9286] = b"ASCII\x00\x00\x00" + fragment.encode()
    img.save(path, "JPEG", quality=88, exif=ex)


def make_chrome_history(path: Path, fragment: str, webkit_us: int):
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("PRAGMA page_size=4096")
    cur.executescript("""
        CREATE TABLE meta(key LONGVARCHAR PRIMARY KEY, value LONGVARCHAR);
        CREATE TABLE urls(id INTEGER PRIMARY KEY, url LONGVARCHAR, title LONGVARCHAR,
                          visit_count INTEGER DEFAULT 1 NOT NULL,
                          typed_count INTEGER DEFAULT 0 NOT NULL,
                          last_visit_time INTEGER NOT NULL, hidden INTEGER DEFAULT 0 NOT NULL);
        CREATE TABLE visits(id INTEGER PRIMARY KEY, url INTEGER NOT NULL,
                            visit_time INTEGER NOT NULL, from_visit INTEGER,
                            transition INTEGER DEFAULT 0 NOT NULL, segment_id INTEGER,
                            visit_duration INTEGER DEFAULT 0 NOT NULL);
    """)
    early = webkit_us - 3600_000_000 * 5
    noise = [
        ("https://habr.com/ru/companies/", "Хабр", early),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "YouTube", early + 600_000_000),
        ("https://yandex.ru/maps/", "Карты", early + 1200_000_000),
        ("https://4pda.to/forum/", "4PDA", early + 1800_000_000),
        ("https://paste.burntnote.onion/k/" + fragment, "burnt paste", webkit_us),
    ]
    for i, (url, title, t) in enumerate(noise, 1):
        cur.execute("INSERT INTO urls VALUES (?,?,?,?,?,?,0)", (i, url, title, 1, 0, t))
        cur.execute("INSERT INTO visits VALUES (?,?,?,0,805306368,0,0)", (i, i, t))
    cur.execute("INSERT INTO meta VALUES ('version','42')")
    con.commit()
    con.close()


def make_msgstore(path: Path, fragment: str, ts_sec: int):
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("PRAGMA page_size=4096")
    cur.executescript("""
        CREATE TABLE messages(_id INTEGER PRIMARY KEY,
                              timestamp INTEGER,
                              media_wa_type INTEGER,
                              key_id TEXT,
                              remote_resource TEXT,
                              text_data TEXT);
        CREATE TABLE chat_list(_id INTEGER PRIMARY KEY, jid TEXT);
    """)
    rows = [
        (1, ts_sec - 86400 * 2, 0, "A1", "79001112233@s.whatsapp.net",
         "Сынок, позвони как сможешь"),
        (2, ts_sec - 86400, 0, "B2", "79001112233@s.whatsapp.net",
         "Ты на работе? Сосед просил помочь с техникой"),
        (3, ts_sec, 0, "C3", "burntnote@s.whatsapp.net",
         "Код подтверждения Burnt Note: " + fragment + ". Никому не сообщайте."),
        (4, ts_sec + 7200, 0, "D4", "news@s.whatsapp.net",
         "Доброе утро!_top-новости за день"),
    ]
    cur.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def make_contacts(path: Path):
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE contacts(_id INTEGER PRIMARY KEY, display_name TEXT);
        CREATE TABLE raw_contacts(_id INTEGER PRIMARY KEY, display_name TEXT, deleted INTEGER DEFAULT 0);
    """)
    cur.executemany("INSERT INTO contacts VALUES (?,?)", [
        (1, "Мама"), (2, "Автосервис"), (3, "Приёмщик")])
    cur.executemany("INSERT INTO raw_contacts VALUES (?,?,0)", [
        (1, "Мама"), (2, "Автосервис"), (3, "Приёмщик")])
    con.commit()
    con.close()


SETTINGS_SECURE = """<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<settings version="214">
    <setting id="1" name="adaptive_sleep" value="1" package="android" defaultValue="0" defaultSysSet="true" tagged="true" />
    <setting id="2" name="android_id" value="{android_id}" package="android" />
    <setting id="3" name="backup_enabled" value="0" package="android" />
    <setting id="4" name="lock_screen_lock_after_timeout" value="5000" package="android" />
    <setting id="5" name="mode_ringer" value="2" package="android" />
</settings>
"""

WIFI_CONFIG = """<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<WifiConfigStoreData>
    <NetworkList>
        <Network>
            <WifiConfiguration>
                <SSID>"Podjezd_3G"</SSID>
                <PreSharedKey>"proverka1212"</PreSharedKey>
                <DefaultGwMacAddress>aa:bb:cc:12:34:56</DefaultGwMacAddress>
                <RandomizedMacRandomness>2</RandomizedMacRandomness>
            </WifiConfiguration>
            <NetworkStatus>
                <NetworkId>0</NetworkId>
                <PasspointInstallerPackage></PasspointInstallerPackage>
            </NetworkStatus>
        </Network>
        <Network>
            <WifiConfiguration>
                <SSID>"Rostelecom_A421"</SSID>
                <PreSharedKey>"12345678"</PreSharedKey>
                <DefaultGwMacAddress>de:ad:be:ef:00:01</DefaultGwMacAddress>
            </WifiConfiguration>
            <NetworkStatus>
                <NetworkId>1</NetworkId>
            </NetworkStatus>
        </Network>
        <Network>
            <WifiConfiguration>
                <SSID>"MD_Free_WiFi"</SSID>
                <DefaultGwMacAddress>02:00:00:00:00:00</DefaultGwMacAddress>
            </WifiConfiguration>
            <NetworkStatus>
                <NetworkId>2</NetworkId>
            </NetworkStatus>
        </Network>
    </NetworkList>
</WifiConfigStoreData>
"""

BURNT_SETTINGS = """<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="device_alias">b-note-77</string>
    <boolean name="self_destruct_enabled" value="true" />
    <int name="burn_after_seconds" value="60" />
    <string name="sync_endpoint">https://sync.burntnote.onion/v1</string>
    <int name="seed_schema" value="1" />
    <int name="local_db_version" value="3" />
</map>
"""

TOMBSTONE = """*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
Build fingerprint: 'samsung/o1sxxx/o1s:14/UP1A.231005.007/12345678:user/release-keys'
Revision: '11'
Timestamp: 2026-01-13 20:12:44.024881674+0300
pid: 21486, tid: 21486, name: ctf.burntnote  >>> com.ctf.burntnote <<<
uid: 10438
signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------
Abort message: 'java.lang.IllegalStateException: sync channel closed: sync.burntnote.onion unreachable'
    r0  0000000000000000  r1  0000000000000000  r2  0000000000000006
    r3  0000000000000000  r4  0000000000000000  r5  0000000000000000
    r6  b400007af35c70c0  r7  0000000000000000  r8  b400007af35c7298
backtrace:
    #00 pc 00000000000a1b2c  /apex/com.android.runtime/lib64/bionic/libc.so (abort+164)
    #01 pc 00000000003e4a90  /data/app/~~fH3x/com.ctf.burntnote-IlQ/lib/arm64/libsync.so
    #02 pc 00000000005af31c  /apex/com.android.art/lib64/libart.so (art::Runtime::Abort(char const*)+116)
    #03 pc 00000000007c1d88  /data/app/~~fH3x/com.ctf.burntnote-IlQ/base.apk
"""


def make_log(fragment: str, ms_times) -> bytes:
    boot, tz_t, wa_t, chrome_t, cam_t, seed_t, seal_t, master_t, sync_t, wipe_t = ms_times
    lines = [
        (boot, "env ok: model=SM-G925F sdk=34 alias=b-note-77"),
        (boot + 312, "storage: local db v3 opened (wal)"),
        (tz_t, "timezone resolved: Europe/Moscow (UTC+03:00)"),
        (wa_t, "im-backup parsed: com.whatsapp/databases/msgstore.db (legacy plaintext)"),
        (chrome_t, "chrome profile scanned: app_chrome/Default/History"),
        (cam_t, "camera roll scanned: 1 candidate(s)"),
        (seed_t, f"seed fragment captured (device entropy): {fragment}"),
        (seal_t, "seed material sealed: 4/4"),
        (master_t, "master key derived: ok (pbkdf2 100000)"),
        (sync_t, "sync unreachable: sync.burntnote.onion (dead onion)"),
        (wipe_t, "wipe scheduler armed: burn_after=60s"),
        (wipe_t + 41000, "total wipe executed: messages=12"),
        (wipe_t + 41001, "goodbye."),
    ]
    return b"".join(f"[{ms}] {msg}\n".encode() for ms, msg in lines)


def main():
    aesgcm.selftest()
    flag = os.environ.get("FLAG", DEFAULT_FLAG)
    if not (flag.startswith("ctfcup{") and flag.endswith("}")):
        sys.exit("FLAG must look like ctfcup{...}")

    rnd = random.Random()  # OS entropy: fragments/nonces vary per build
    def frag():
        return "".join(rnd.choices("0123456789abcdef", k=SEED_LEN_HEX))

    f_wa, f_exif, f_log, f_chrome = frag(), frag(), frag(), frag()
    android_id = "".join(rnd.choices("0123456789abcdef", k=16))

    # -- seed material, ordered by UTC ------------------------------------
    ordered = [
        ("whatsapp_sec", f_wa, T_WA_SEC),
        ("exif_local", f_exif, T_EXIF_UTC),
        ("log_ms", f_log, T_LOG_MS),
        ("chrome_webkit", f_chrome, T_CHROME_WEBKIT),
    ]
    ordered.sort(key=lambda x: x[2])
    seed_string = "-".join(h for _, h, _ in ordered)

    texts = [t for _, t in MESSAGES]
    texts[11] = FLAG_TPL.format(flag=flag)
    plaintexts = [pad(t) for t in texts]

    master, keys = derive_keys(seed_string, android_id, plaintexts)

    rows = []
    created = int(CHAT_START.timestamp() * 1000)
    for i in range(12):
        nonce = bytes(rnd.getrandbits(8) for _ in range(12))
        aad = f"burnt-note/msg/{i + 1}".encode()
        frame = aesgcm.gcm_encrypt(keys[i], nonce, aad, plaintexts[i])
        assert len(frame) == PAD_LEN + 16
        rows.append((i + 1, created, texts[i][0] and MESSAGES[i][0] or "R",
                     nonce, frame))
        created += CHAT_STEP_MS

    # author-only summary, written as soon as all key material exists
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True, exist_ok=True)
    summary = {
        "flag": flag,
        "android_id": android_id,
        "seed_string": seed_string,
        "master_key": master.hex(),
        "fragments_utc_order": [
            {"source": src, "fragment": h, "utc": t.isoformat()}
            for src, h, t in ordered],
        "message_keys": {str(i + 1): keys[i].hex() for i in range(12)},
        "rows": [
            {"id": r[0], "created_at_utc": datetime.fromtimestamp(
                r[1] / 1000, timezone.utc).isoformat(), "sender": r[2],
             "nonce": r[3].hex()} for r in rows],
    }
    (BUILD / "build_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[build] author summary: {BUILD / 'build_summary.json'}")

    # -- staging ----------------------------------------------------------
    staging = BUILD / "staging"
    app = staging / "data/data/com.ctf.burntnote"
    (app / "databases").mkdir(parents=True)
    (app / "shared_prefs").mkdir(parents=True)
    (app / "files").mkdir(parents=True)
    (staging / "data/data/com.whatsapp/databases").mkdir(parents=True)
    (staging / "data/data/com.android.chrome/app_chrome/Default").mkdir(parents=True)
    (staging / "data/data/com.android.providers.contacts/databases").mkdir(parents=True)
    (staging / "data/misc/wifi").mkdir(parents=True)
    (staging / "data/secure/0").mkdir(parents=True)
    (staging / "data/tombstones").mkdir(parents=True)
    (staging / "sdcard/DCIM/Camera").mkdir(parents=True)

    # messages.db + WAL (copied while the connection is open, pre-checkpoint)
    dbwork = BUILD / "dbwork"
    dbwork.mkdir()
    con = build_messages_db(dbwork / "messages.db", rows)
    shutil.copyfile(dbwork / "messages.db", app / "databases/messages.db")
    shutil.copyfile(dbwork / "messages.db-wal", app / "databases/messages.db-wal")
    con.close()
    inject_decoy_candidate(app / "databases/messages.db", rows[0])
    wal_path = app / "databases/messages.db-wal"
    wal = bytearray(wal_path.read_bytes())
    wal[0:8] = b"\x00" * 8  # kill magic+version: sqlite ignores, no auto-checkpoint
    wal_path.write_bytes(wal)

    (app / "shared_prefs/burnt_settings.xml").write_text(BURNT_SETTINGS)

    wipe_epoch_ms = created + 41000
    log_bytes = make_log(f_log, ms_times=[
        int((DAY + timedelta(hours=9, minutes=41)).timestamp() * 1000),   # boot
        int((DAY + timedelta(hours=16, minutes=0, seconds=5)).timestamp() * 1000),  # tz
        int((T_WA_SEC + timedelta(seconds=140)).timestamp() * 1000),     # wa scanned
        int((T_CHROME_WEBKIT - timedelta(seconds=95)).timestamp() * 1000),  # chrome
        int((T_EXIF_UTC + timedelta(seconds=64)).timestamp() * 1000),    # camera
        int(T_LOG_MS.timestamp() * 1000),                                # fragment!
        int((T_LOG_MS + timedelta(seconds=20)).timestamp() * 1000),      # sealed
        int((T_LOG_MS + timedelta(seconds=40)).timestamp() * 1000),      # master ok
        int((DAY + timedelta(hours=17, minutes=10)).timestamp() * 1000),  # sync dead
        int((DAY + timedelta(hours=17, minutes=40)).timestamp() * 1000),  # armed
    ])
    (app / "files/diagnostics.log").write_bytes(log_bytes)
    (app / "files/release.lock").write_bytes(
        b"BN-PRO-7712\nsubscription=pro\nwipe_on_tamper=1\n")

    make_msgstore(staging / "data/data/com.whatsapp/databases/msgstore.db",
                  f_wa, int(T_WA_SEC.timestamp()))
    make_chrome_history(
        staging / "data/data/com.android.chrome/app_chrome/Default/History",
        f_chrome, int(T_CHROME_WEBKIT.timestamp() + WEBKIT_EPOCH_DELTA) * 1_000_000)
    make_contacts(
        staging / "data/data/com.android.providers.contacts/databases/contacts2.db")
    (staging / "data/misc/wifi/WifiConfigStore.xml").write_text(WIFI_CONFIG)
    (staging / "data/secure/0/settings_secure.xml").write_text(
        SETTINGS_SECURE.format(android_id=android_id))
    (staging / "data/tombstones/tombstone_00").write_text(TOMBSTONE)
    make_jpeg(staging / "sdcard/DCIM/Camera/IMG_20260113_192401.jpg", f_exif)

    # -- author self-check part 1: inventory --------------------------------
    main_bytes = (app / "databases/messages.db").read_bytes()
    wal_bytes = (app / "databases/messages.db-wal").read_bytes()
    assert main_bytes[:16] == b"SQLite format 3\x00"
    assert wal_bytes[:8] == b"\x00" * 8 and len(wal_bytes) > 32
    ids_main = {r.rowid for r in sqlcarve.dedupe_by_time(
        sqlcarve.carve_db(main_bytes))}
    ids_wal = {r.rowid for r in sqlcarve.dedupe_by_time(
        sqlcarve.carve_wal(wal_bytes))}
    assert {1, 2, 3, 4, 5, 6, 7} <= ids_main, f"main db carve got {ids_main}"
    assert not ids_main & {8, 9, 10, 11, 12}, \
        f"wal-only rows leaked into main db: {ids_main}"
    assert {8, 9, 10, 11, 12} <= ids_wal, f"wal carve got {ids_wal}"

    # what a plain sqlite3 query sees (WAL ignored because its magic is gone):
    # the phase-A state minus the two burned-after-reading messages
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        tmp.write(main_bytes)
        tmp.flush()
        vis = sqlite3.connect(tmp.name).execute(
            "SELECT id FROM messages ORDER BY id").fetchall()
        assert {v[0] for v in vis} == {1, 3, 5, 6, 7}, f"visible rows: {vis}"
    print("[selfcheck] row inventory and visible rows as designed")

    # EXIF round-trip check
    from PIL import Image
    img = Image.open(staging / "sdcard/DCIM/Camera/IMG_20260113_192401.jpg")
    ex = img.getexif()
    assert ex[0x9286] == b"ASCII\x00\x00\x00" + f_exif.encode(), "EXIF UserComment lost"
    assert ex[0x9003] == T_EXIF_LOCAL.strftime("%Y:%m:%d %H:%M:%S")
    assert ex[0x9010] == "+03:00"
    print("[selfcheck] EXIF UserComment/DateTimeOriginal/OffsetTime round-trip OK")

    # -- tar ---------------------------------------------------------------
    HANDOUT.mkdir(exist_ok=True)
    out = HANDOUT / "evidence.tar.gz"
    mtimes = {}
    with tarfile.open(out, "w:gz") as tf:
        for p in sorted(staging.rglob("*")):
            if not p.is_file():
                continue
            arcname = "/" + p.relative_to(staging).as_posix()
            info = tf.gettarinfo(str(p), arcname=arcname)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mode = 0o600 if "/data/" in arcname else 0o644
            info.mtime = int(wipe_epoch_ms / 1000)
            with open(p, "rb") as fh:
                tf.addfile(info, fh)
            mtimes[arcname] = info.mtime
    print(f"[build] {out} ({out.stat().st_size} bytes)")

    # -- author self-check part 2: solve the produced archive end-to-end ----
    sys.path.insert(0, str(TASK / "solve"))
    import solve as authorsolver
    res = authorsolver.solve_archive(out.read_bytes())
    assert len(res["messages"]) == 12, "solver must recover 12 messages"
    assert res["flag"] == flag, f"solver flag mismatch: {res['flag']!r}"
    print("[selfcheck] solver recovered 12 messages and the flag from the "
          "final archive")


if __name__ == "__main__":
    main()
