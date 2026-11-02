#!/usr/bin/env python3
"""Local end-to-end test: anvil + deploy + daemon + solver -> isSolved().

Usage: python3 tools/e2e.py [N=3] [budget=10] [factor_bits=40]
Run from the task directory (or anywhere; paths are resolved).
"""

import os
import random
import re
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)              # task dir (misc/flygammon)
FLY = os.path.join(ROOT, "flygammon")     # the Rust model crate
PROJ = os.path.join(ROOT, "challenge", "project")
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
if not os.path.exists(VENV_PY):           # solver needs numpy; use it if venv exists
    VENV_PY = sys.executable
DAEMON = os.path.join(ROOT, "daemon", "target", "release", "flygammon-daemon")

sys.path.insert(0, HERE)
import dlp  # noqa: E402

RPC = "http://127.0.0.1:8545"
# anvil default-mnemonic accounts
DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
PLAYER_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
PLAYER_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
ORACLE_KEY = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"
ORACLE_ADDR = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"

procs = []


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


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    budget = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    factor_bits = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    seed = 12345

    print(f"[e2e] N={n} budget={budget} factor_bits={factor_bits}")
    p, fac = dlp.gen_smooth_prime(256, factor_bits, seed=seed)
    g = dlp.primitive_root(p, fac)
    rng = random.Random(seed)
    s = rng.randrange(2, p - 1)
    h = pow(g, s, p)
    print(f"[e2e] params ready (p~2^{p.bit_length()}, g={g})")

    # anvil
    anvil = subprocess.Popen(
        ["anvil", "--gas-limit", "300000000000", "--base-fee", "0", "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    procs.append(anvil)
    time.sleep(2.0)

    # deploy
    out = subprocess.run(
        ["forge", "create", "src/Flygammon.sol:Flygammon", "--rpc-url", RPC,
         "--private-key", DEPLOYER_KEY, "--broadcast", "--constructor-args",
         str(p), str(g), str(h), PLAYER_ADDR, ORACLE_ADDR, str(n), str(budget)],
        cwd=PROJ, capture_output=True, text=True,
    )
    m = re.search(r"Deployed to:\s*(0x[0-9a-fA-F]{40})", out.stdout)
    if not m:
        print("[e2e] deploy failed:\n", out.stdout, out.stderr)
        cleanup()
        sys.exit(1)
    addr = m.group(1)
    print(f"[e2e] deployed challenge at {addr}")

    # daemon
    denv = dict(os.environ)
    denv.update(dict(
        RPC_URL=RPC, ORACLE_KEY=ORACLE_KEY, CHALLENGE_ADDR=addr,
        PARAM_P=str(p), PARAM_G=str(g), PARAM_H=str(h), ORACLE_S=str(s),
        MODEL_STEM=os.path.join(FLY, "attempts", "h80_i100_distill", "flygammon_best"), HIDDEN="80",
    ))
    daemon = subprocess.Popen([DAEMON], env=denv)
    procs.append(daemon)

    # solver
    senv = dict(os.environ)
    senv.update(dict(
        RPC_URL=RPC, CHALLENGE_ADDR=addr, PLAYER_KEY=PLAYER_KEY,
        MODEL_FLY=os.path.join(FLY, "attempts", "h80_i100_distill", "flygammon_best.fly"), HIDDEN="80",
    ))
    t0 = time.time()
    solver = subprocess.run([VENV_PY, os.path.join(ROOT, "solve", "solve.py")], env=senv)
    dt = time.time() - t0

    # verify
    solved = subprocess.run(
        ["cast", "call", addr, "isSolved()(bool)", "--rpc-url", RPC],
        capture_output=True, text=True,
    ).stdout.strip()
    streak = subprocess.run(
        ["cast", "call", addr, "streak()(uint256)", "--rpc-url", RPC],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"[e2e] solver rc={solver.returncode} in {dt:.1f}s  isSolved={solved} streak={streak}")
    cleanup()
    sys.exit(0 if solved.startswith("true") else 2)


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
