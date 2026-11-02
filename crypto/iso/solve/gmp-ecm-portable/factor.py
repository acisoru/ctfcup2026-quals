#!/usr/bin/env python3
import argparse
import decimal
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time

PORTABLE_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOR_RE = re.compile(r"Factor found in step [12]:\s*(\d+)")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_bound(value):
    s = value.strip().replace("_", "")
    mult = {"k": 10**3, "m": 10**6, "g": 10**9, "t": 10**12}
    try:
        if s and s[-1].lower() in mult:
            return int(decimal.Decimal(s[:-1]) * mult[s[-1].lower()])
        return int(decimal.Decimal(s))
    except Exception:
        raise argparse.ArgumentTypeError(f"invalid integer bound: {value!r}")


def load_n(value):
    text = open(value).read() if os.path.isfile(value) else value
    text = re.sub(r"\s+", "", text).replace("_", "")
    try:
        n = int(text, 0)
    except ValueError:
        raise SystemExit(f"error: cannot parse N from {value!r} (decimal or 0x hex)")
    if n <= 1:
        raise SystemExit("error: N must be > 1")
    return n


def trial_divide(n, limit):
    if limit <= 1:
        return n, []
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for i in range(2, int(limit**0.5) + 1):
        if sieve[i]:
            sieve[i * i:limit + 1:i] = b"\x00" * (((limit - i * i) // i) + 1)
    factors = []
    m = n
    for p in range(2, limit + 1):
        if sieve[p] and m % p == 0:
            while m % p == 0:
                m //= p
            factors.append(p)
    return m, factors


def read_log(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def monitor(procs, logs, found, stop_all):
    while any(p.poll() is None for p in procs):
        if stop_all.is_set():
            for p in procs:
                if p.poll() is None:
                    p.terminate()
            break
        for path in logs:
            if FACTOR_RE.search(read_log(path)):
                found.set()
                stop_all.set()
                for p in procs:
                    if p.poll() is None:
                        p.terminate()
                break
        time.sleep(0.25)
    for p in procs:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def run_parallel(cmds, logs, stop_on_factor=True):
    handles = []
    procs = []
    for cmd, path in zip(cmds, logs):
        fh = open(path, "w")
        handles.append(fh)
        procs.append(subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT))
    if stop_on_factor:
        found = threading.Event()
        stop_all = threading.Event()
        t = threading.Thread(target=monitor, args=(procs, logs, found, stop_all))
        t.start()
        t.join()
        rc = found.is_set()
    else:
        for p in procs:
            p.wait()
        rc = False
    for fh in handles:
        fh.close()
    return rc


def parse_factors(n, paths):
    factors = set()
    for path in paths:
        for m in FACTOR_RE.finditer(read_log(path)):
            f = int(m.group(1))
            if 1 < f < n and n % f == 0:
                factors.add(f)
    return factors


def strip_factors(n, factors):
    for f in sorted(factors):
        while True:
            g = math.gcd(n, f)
            if g == 1:
                break
            n //= g
    return n


def write_n(path, n):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        f.write(str(n) + "\n")
    os.replace(tmp, path)


def split_lines(save_paths, outdir, chunks, rng):
    lines = []
    for path in save_paths:
        try:
            with open(path) as f:
                lines.extend(line for line in f if line.strip())
        except FileNotFoundError:
            pass
    total = len(lines)
    if total == 0:
        return 0, []
    rng.shuffle(lines)
    chunks = min(chunks, total)
    paths = []
    for i in range(chunks):
        lo = total * i // chunks
        hi = total * (i + 1) // chunks
        p = os.path.join(outdir, f"resume_{i:03d}.save")
        with open(p, "w") as f:
            f.writelines(lines[lo:hi])
        paths.append(p)
    return total, paths


def detect_devices(spec):
    if spec.strip().lower() == "all":
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"], text=True
        )
        return [int(x) for x in out.split()]
    return [int(x) for x in spec.split(",") if x.strip() != ""]


def main():
    ap = argparse.ArgumentParser(description="GPU ECM pipeline: GPU stage 1 + parallel CPU stage 2")
    ap.add_argument("--n", required=True, help="N as decimal/hex integer or path to a file")
    ap.add_argument("--b1", type=parse_bound, required=True, help="stage 1 bound, e.g. 3000000 or 3M")
    ap.add_argument("--b2", type=parse_bound, required=True, help="stage 2 bound, e.g. 10000000 or 10M")
    ap.add_argument("--devices", default="0", help="comma-separated GPU ids or 'all'")
    ap.add_argument("--threads", "--cpu-cores", dest="threads", type=int,
                    default=os.cpu_count() or 1, help="CPU threads for stage 2")
    ap.add_argument("--waves", type=int, default=1,
                    help="number of ECM batches; found factors are stripped between waves")
    ap.add_argument("--curves", type=int, default=4096, help="curves per GPU per wave")
    ap.add_argument("--maxmem", type=int, default=0, help="stage 2 maxmem per process, MB (0=default)")
    ap.add_argument("--workdir", default=os.path.join(PORTABLE_DIR, "runs"))
    ap.add_argument("--ecm", default=os.path.join(PORTABLE_DIR, "bin", "ecm"))
    ap.add_argument("--seed", type=int, default=None, help="seed for sigma/shuffle reproducibility")
    ap.add_argument("--trial-limit", type=int, default=0,
                    help="strip prime factors up to this bound before ECM (0=off)")
    ap.add_argument("--stop-on-factor", action="store_true",
                    help="stop after the first wave that finds a factor")
    args = ap.parse_args()

    if args.b2 <= args.b1:
        raise SystemExit("error: --b2 must be greater than --b1")
    if args.threads < 1:
        raise SystemExit("error: --threads must be >= 1")
    if args.waves < 1:
        raise SystemExit("error: --waves must be >= 1")
    if not os.path.isfile(args.ecm) or not os.access(args.ecm, os.X_OK):
        raise SystemExit(f"error: ecm binary not found at {args.ecm}; run build.sh first")

    devices = detect_devices(args.devices)
    if not devices:
        raise SystemExit("error: no GPU devices selected")

    c = args.curves
    if c % 32:
        c = (c // 32 + 1) * 32
        log(f"curves rounded up to a multiple of 32: {c}")
    if c < 1024:
        log("warning: fewer than 1024 curves per batch may underfill the GPU")

    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    os.makedirs(args.workdir, exist_ok=True)
    run_dir = tempfile.mkdtemp(prefix="run_", dir=args.workdir)

    n = load_n(args.n)
    n, small = trial_divide(n, args.trial_limit)
    if small:
        log(f"trial division stripped factors: {small}")
        log(f"remaining N = {n.bit_length()} bits")
    if n == 1:
        log("N fully factored by trial division")
        return 0

    n_path = os.path.join(run_dir, "n_wave_00.txt")
    write_n(n_path, n)
    n_start = n

    log(f"N={n.bit_length()} bits, B1={args.b1}, B2={args.b2}, "
        f"curves/gpu/wave={c}, devices={devices}, threads={args.threads}, "
        f"waves={args.waves}, dir={run_dir}")

    t_start = time.monotonic()
    curves_done = 0
    all_factors = set()

    for wave in range(args.waves):
        wdir = os.path.join(run_dir, f"wave_{wave:02d}")
        os.makedirs(wdir)
        base = rng.randrange(2, 1 << 31)
        cmds, logs, saves = [], [], []
        for i, dev in enumerate(devices):
            save = os.path.join(wdir, f"stage1_dev{dev}.save")
            lg = os.path.join(wdir, f"stage1_dev{dev}.log")
            sigma = base + i * c
            cmds.append([
                args.ecm, "-gpu", "-gpudevice", str(dev), "-gpucurves", str(c),
                "-c", str(c), "-sigma", f"3:{sigma}", "-save", save,
                "-inp", n_path, str(args.b1), "0",
            ])
            logs.append(lg)
            saves.append(save)

        log(f"wave {wave}: step 1 on GPUs {devices} ({c} curves each)")
        t0 = time.monotonic()
        run_parallel(cmds, logs, stop_on_factor=True)
        dt1 = time.monotonic() - t0
        curves_done += len(devices) * c
        f1 = parse_factors(n, logs)
        log(f"wave {wave}: step 1 done in {dt1:.0f}s, factors: {sorted(f1)}")
        if f1:
            all_factors |= f1
            log(f"wave {wave}: divisors found in this wave:")
            for f in sorted(f1):
                log(f"  {f} ({f.bit_length()} bits), cofactor {(n // f).bit_length()} bits")
            n = strip_factors(n, f1)
            n_path = os.path.join(run_dir, f"n_wave_{wave + 1:02d}.txt")
            write_n(n_path, n)
            log(f"wave {wave}: remaining N = {n.bit_length()} bits -> {n_path}")
            if args.stop_on_factor or n == 1:
                break
            continue

        total, chunk_paths = split_lines(saves, wdir, args.threads, rng)
        if total == 0:
            for lg in logs:
                tail = read_log(lg)[-500:]
                if tail:
                    print(tail, file=sys.stderr)
            raise SystemExit("error: no stage 1 residues saved (see logs above)")

        log(f"wave {wave}: step 2 on {total} residues over {len(chunk_paths)} processes")
        cmds, logs = [], []
        for i, p in enumerate(chunk_paths):
            lg = os.path.join(wdir, f"stage2_{i:03d}.log")
            cmd = [args.ecm, "-resume", p, str(args.b1), str(args.b2)]
            if args.maxmem:
                cmd += ["-maxmem", str(args.maxmem)]
            cmds.append(cmd)
            logs.append(lg)

        t0 = time.monotonic()
        run_parallel(cmds, logs, stop_on_factor=True)
        dt2 = time.monotonic() - t0
        f2 = parse_factors(n, logs)
        log(f"wave {wave}: step 2 done in {dt2:.0f}s, factors: {sorted(f2)}")
        if f2:
            all_factors |= f2
            log(f"wave {wave}: divisors found in this wave:")
            for f in sorted(f2):
                log(f"  {f} ({f.bit_length()} bits), cofactor {(n // f).bit_length()} bits")
            n = strip_factors(n, f2)
            n_path = os.path.join(run_dir, f"n_wave_{wave + 1:02d}.txt")
            write_n(n_path, n)
            log(f"wave {wave}: remaining N = {n.bit_length()} bits -> {n_path}")
            if args.stop_on_factor or n == 1:
                break
        else:
            log(f"wave {wave}: no divisors found")

    elapsed = time.monotonic() - t_start
    if all_factors:
        log("ALL DIVISORS FOUND:")
        for f in sorted(all_factors):
            cof = n_start // f
            log(f"  {f} ({f.bit_length()} bits), cofactor {cof.bit_length()} bits")
        if n > 1:
            log(f"  remaining N = {n.bit_length()} bits -> {n_path}")
        log(f"TOTAL WALL: {elapsed:.1f}s ({elapsed / 60:.2f} min), "
            f"curves requested: {curves_done}")
        return 0

    log(f"no factor found after {args.waves} wave(s)")
    log(f"TOTAL WALL: {elapsed:.1f}s ({elapsed / 60:.2f} min), "
        f"curves requested: {curves_done}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
