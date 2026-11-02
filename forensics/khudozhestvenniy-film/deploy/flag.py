#!/usr/bin/env python3
"""
Compute the Lucky Spire flag from the chain + ground truth.

    flag = ctfcup{ keccak256( A || B || C || D )[:16 bytes] }

where (tight-packed concatenation, encodePacked-style):
    A = rogue oracle address            (20 bytes)
    B = insider address                 (20 bytes)
    C = collision slot (uint256)        (32 bytes)   -- the casino oracle slot = 2
    D = rigged engine codehash          (32 bytes)

Run with a loaded node on :8545 (see public/readme.md).
"""
import subprocess, json, os, sys

RPC = os.environ.get("RPC", "http://127.0.0.1:8545")
COLLISION_SLOT = 2          # Casino.oracle lives at storage slot 2; the rigged write collides here
FLAG_BYTES     = 16         # truncate the 32-byte hash to this many bytes

def sh(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(a)}\n{r.stderr}")
    return r.stdout.strip()

def find_rigged_block(H, honest_hash):
    """Scan history for a block where H's codehash differs from the honest (final) one.
    Binary-ish: step through blocks; the first mismatch is inside an attack window."""
    latest = int(sh("cast", "block-number", "--rpc-url", RPC).split()[0])
    # coarse scan every ~5 blocks is enough — windows are tens of blocks wide
    for b in range(1, latest + 1, 3):
        code = sh("cast", "code", H, "--rpc-url", RPC, "--block", str(b))
        if len(code) > 2 and sh("cast", "keccak", code) != honest_hash:
            return b, sh("cast", "keccak", code)
    raise RuntimeError("no block found where H holds non-honest code")

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ans = json.load(open(os.path.join(here, "answer.json")))

    A = ans["rogue_oracle"].lower()
    B = ans["insider"].lower()
    H = ans["engine_H"]

    # honest codehash = H's code at the latest block (engine restored after the last window)
    honest_code = sh("cast", "code", H, "--rpc-url", RPC)
    if len(honest_code) <= 2:
        print("[!] no code at H at latest — is the node loaded? (block-number must be > 0)",
              file=sys.stderr)
        sys.exit(1)
    honest_hash = sh("cast", "keccak", honest_code)

    # D = rigged codehash, found by scanning history for a window where H's code differs
    window_block, D = find_rigged_block(H, honest_hash)
    print(f"[*] rigged engine live at block {window_block}")
    assert honest_hash != D, "rigged and honest codehash are equal — wrong window block?"

    # preimage = concatenation of hex STRINGS (no 0x, lowercase, fixed width):
    #   A(40) + B(40) + C(64) + D(64) = 208 hex chars. keccak256 is taken over this TEXT
    #   (the ASCII bytes of the hex string), not over the packed bytes.
    preimage = (
        A[2:].rjust(40, "0") +
        B[2:].rjust(40, "0") +
        f"{COLLISION_SLOT:064x}" +
        D[2:].rjust(64, "0")
    ).lower()
    digest = sh("cast", "keccak", preimage)   # no 0x -> hash the hex STRING as text
    flag_hex = digest[2:2 + FLAG_BYTES * 2]
    flag = f"ctfcup{{{flag_hex}}}"

    print("A (rogue oracle) :", A)
    print("B (insider)      :", B)
    print("C (collision slot):", COLLISION_SLOT)
    print("D (rigged codehash):", D)
    print("honest codehash   :", honest_hash)
    print("preimage (hex text):", preimage)
    print("keccak256(text)   :", digest)
    print()
    print("FLAG:", flag)
    return flag

if __name__ == "__main__":
    main()
