#!/usr/bin/env python3
"""Host-level instance test mirroring challenge/entrypoint.sh (no Docker):
anvil + deploy + daemon + rpc_proxy + launcher, then the solver drives the game
THROUGH the proxy, we read the flag from the launcher socket, and we confirm the
proxy blocks a cheat RPC. Validates the infra pieces the container just wraps.

Usage: python3 tools/instance_local.py [N=2] [budget=10] [factor_bits=24]
"""

import json
import os
import random
import re
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)              # task dir (misc/flygammon)
FLY = os.path.join(ROOT, "flygammon")     # the Rust model crate
PROJ = os.path.join(ROOT, "challenge", "project")
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
if not os.path.exists(VENV_PY):           # solver needs numpy; use it if venv exists
    VENV_PY = sys.executable
DAEMON = os.path.join(ROOT, "daemon", "target", "release", "flygammon-daemon")
PROXY_BIN = os.path.join(ROOT, "daemon", "target", "release", "flygammon-proxy")

sys.path.insert(0, HERE)
import dlp

INTERNAL = "http://127.0.0.1:8546"
PROXY = "http://127.0.0.1:8545"
LAUNCHER_PORT = 1337
FLAG = "flag{the_fly_never_rolled_a_secret}"
DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
procs = []


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def cleanup():
    for p in procs:
        try:
            p.send_signal(signal.SIGTERM)
        except Exception:
            pass
    time.sleep(0.5)
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass


def new_key():
    k = "0x" + secrets.token_hex(32)
    addr = sh(["cast", "wallet", "address", k]).stdout.strip()
    return k, addr


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    budget = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    factor_bits = int(sys.argv[3]) if len(sys.argv) > 3 else 24

    p, fac = dlp.gen_smooth_prime(256, factor_bits)
    g = dlp.primitive_root(p, fac)
    s = random.randrange(2, p - 1)
    h = pow(g, s, p)

    procs.append(subprocess.Popen(
        ["anvil", "--port", "8546", "--gas-limit", "300000000000", "--base-fee", "0", "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(2)

    player_key, player_addr = new_key()
    oracle_key, oracle_addr = new_key()
    for a in (player_addr, oracle_addr):
        sh(["cast", "send", a, "--value", "100ether", "--private-key", DEPLOYER_KEY, "--rpc-url", INTERNAL])

    out = sh(["forge", "create", "src/Flygammon.sol:Flygammon", "--rpc-url", INTERNAL,
              "--private-key", DEPLOYER_KEY, "--broadcast", "--constructor-args",
              str(p), str(g), str(h), player_addr, oracle_addr, str(n), str(budget)], cwd=PROJ)
    m = re.search(r"Deployed to:\s*(0x[0-9a-fA-F]{40})", out.stdout)
    addr = m.group(1)
    print(f"[inst] deployed {addr}")

    denv = dict(os.environ, RPC_URL=INTERNAL, ORACLE_KEY=oracle_key, CHALLENGE_ADDR=addr,
                PARAM_P=str(p), PARAM_G=str(g), PARAM_H=str(h), ORACLE_S=str(s),
                MODEL_STEM=os.path.join(FLY, "attempts", "h80_i100_distill", "flygammon_best"), HIDDEN="80")
    procs.append(subprocess.Popen([DAEMON], env=denv))

    flag_file = os.path.join(tempfile.gettempdir(), "flygammon_flag.txt")
    with open(flag_file, "w") as fh:
        fh.write(FLAG)
    penv = dict(os.environ, CHALLENGE_ADDR=addr, PLAYER_KEY=player_key, PUBLIC_RPC=PROXY,
                FLAG_FILE=flag_file, WIN_N=str(n))
    procs.append(subprocess.Popen([PROXY_BIN, "8545", INTERNAL], env=penv))
    time.sleep(1.5)

    # --- proxy must reject a cheat method ---
    req = urllib.request.Request(PROXY, data=json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "anvil_setStorageAt",
         "params": [addr, "0x0", "0x" + "11" * 32]}).encode(),
        headers={"Content-Type": "application/json"})
    cheat = json.loads(urllib.request.urlopen(req, timeout=10).read())
    blocked = "error" in cheat and "not permitted" in cheat["error"]["message"]
    print(f"[inst] proxy blocks anvil_setStorageAt: {blocked}")

    # --- solver drives the game THROUGH the proxy ---
    senv = dict(os.environ, RPC_URL=PROXY, CHALLENGE_ADDR=addr, PLAYER_KEY=player_key,
                MODEL_FLY=os.path.join(FLY, "attempts", "h80_i100_distill", "flygammon_best.fly"), HIDDEN="80",
                PREVIEW="1")
    t0 = time.time()
    solver = subprocess.run([VENV_PY, os.path.join(ROOT, "solver", "solve.py")], env=senv)
    print(f"[inst] solver rc={solver.returncode} in {time.time()-t0:.1f}s")

    # --- read the flag from the launcher socket ---
    with urllib.request.urlopen(PROXY + "/flag", timeout=10) as r:
        resp = r.read().decode(errors="ignore")
    got_flag = FLAG in resp
    print(f"[inst] GET /flag served flag: {got_flag}  -> {resp.strip()}")

    cleanup()
    ok = blocked and got_flag and solver.returncode == 0
    print(f"[inst] RESULT: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
