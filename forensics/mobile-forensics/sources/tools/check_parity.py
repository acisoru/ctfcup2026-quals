#!/usr/bin/env python3
"""Java <-> Python crypto parity check for Burnt Note.

Compiles the APK's pure-java crypto classes (BurntCrypto, SeedFragment) with
javac and verifies that master/key derivation and the AES-GCM frame are
byte-identical to the reference implementation used by the evidence
generator (tools/aesgcm.py) and the solver.

Exit code 0 = parity. Run from anywhere.
"""

import hashlib
import hmac
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
CRYPTO = TASK / "android/app/src/main/java/com/ctf/burntnote/crypto"

sys.path.insert(0, str(HERE))
import aesgcm  # noqa: E402

SEED = "aabbccddeeff-112233445566-778899aabbcc-deadbeef0123"
ANDROID_ID = "0123456789abcdef"
TEXT1 = "Выхожу на смену. Сегодня по старой схеме?"
NONCE = bytes.fromhex("deadbeefcafe0123456789ab")[:12]


def reference():
    master = hashlib.pbkdf2_hmac(
        "sha256", SEED.encode(), ANDROID_ID.encode(), 100_000, 32)
    k1 = hmac.new(master, b"burnt-note/root", hashlib.sha256).digest()
    padded = TEXT1.encode().ljust(1400, b"\x00")
    k2 = hmac.new(k1, padded + b"|burnt-note/step|2", hashlib.sha256).digest()
    frame = aesgcm.gcm_encrypt(k1, NONCE, b"burnt-note/msg/1", padded)
    return master.hex(), k1.hex(), k2.hex(), frame.hex()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        harness = HERE / "parity/ParityHarness.java"
        javac = os.environ.get("JAVAC", "javac")
        subprocess.run(
            [javac, "-encoding", "UTF-8", "-source", "8", "-target", "8",
             "-d", str(tmp),
             str(CRYPTO / "BurntCrypto.java"),
             str(CRYPTO / "SeedFragment.java"),
             str(harness)],
            check=True)
        out = subprocess.run(
            ["java", "-cp", str(tmp), "ParityHarness",
             SEED, ANDROID_ID, TEXT1, NONCE.hex()],
            check=True, capture_output=True, text=True).stdout.strip().splitlines()
    got = out[0], out[1], out[2], out[3]
    want = reference()
    names = ("master", "key1", "key2", "frame1")
    ok = True
    for name, g, w in zip(names, got, want):
        status = "OK " if g == w else "FAIL"
        ok &= g == w
        print(f"[{status}] {name}: java={g[:32]}... ref={w[:32]}...")
    print(f"[{'OK ' if out[4] == 'true' else 'FAIL'}] java roundtrip")
    print("PARITY: " + ("PASS" if ok and out[4] == "true" else "FAIL"))
    return 0 if ok and out[4] == "true" else 1


if __name__ == "__main__":
    sys.exit(main())
