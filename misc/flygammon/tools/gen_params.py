#!/usr/bin/env python3
"""Generate and sanity-check the VRF parameters (p, g, s, h) for an instance.

- p: ~256-bit prime with p-1 squarefree and smooth (largest factor ~factor_bits).
- g: a primitive root mod p.
- s: the oracle secret, random in [2, p-2].
- h = g^s mod p: the public key handed to the player.

Then it RECOVERS s from h via Pohlig-Hellman (the intended break) and prints the
wall-clock time, so we can calibrate difficulty ("seconds-to-minutes").

Usage: python3 gen_params.py [total_bits=256] [factor_bits=40] [seed]
"""

import sys
import time
import random

import dlp


def main():
    total_bits = int(sys.argv[1]) if len(sys.argv) > 1 else 256
    factor_bits = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else None

    t0 = time.time()
    p, fac = dlp.gen_smooth_prime(total_bits, factor_bits, seed=seed)
    g = dlp.primitive_root(p, fac)
    rng = random.Random(seed) if seed is not None else random
    s = rng.randrange(2, p - 1)
    h = pow(g, s, p)
    t_gen = time.time() - t0

    largest = max(fac)
    print(f"# generated in {t_gen:.2f}s")
    print(f"p = {p}")
    print(f"g = {g}")
    print(f"s = {s}   # SECRET (oracle only)")
    print(f"h = {h}")
    print(f"# p bit length: {p.bit_length()}")
    print(f"# p-1 factors ({len(fac)}): {sorted(fac)}")
    print(f"# largest factor: {largest} (~2^{largest.bit_length()})")

    # The intended break: recover s from (g, h, p).
    t0 = time.time()
    s_rec = dlp.discrete_log(g, h, p, fac)
    t_dlp = time.time() - t0
    ok = s_rec == s
    print(f"# DLP recovered s in {t_dlp:.2f}s  (correct={ok})")
    if not ok:
        print(f"#   expected {s}")
        print(f"#   got      {s_rec}")
        sys.exit(1)

    # Emit a machine-readable block for Deploy / daemon / solver.
    print("---PARAMS-JSON---")
    print(
        '{{"p": {p}, "g": {g}, "s": {s}, "h": {h}, "factor_bits": {fb}, "dlp_seconds": {ts:.3f}}}'.format(
            p=p, g=g, s=s, h=h, fb=factor_bits, ts=t_dlp
        )
    )


if __name__ == "__main__":
    main()
