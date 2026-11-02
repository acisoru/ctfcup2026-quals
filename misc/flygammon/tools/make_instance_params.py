#!/usr/bin/env python3
"""Emit fresh per-instance VRF params as shell assignments (no DLP solve — that's
the player's job). Usage: make_instance_params.py [factor_bits=40]"""

import random
import sys

import dlp


def main():
    factor_bits = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    p, fac = dlp.gen_smooth_prime(256, factor_bits)
    g = dlp.primitive_root(p, fac)
    s = random.SystemRandom().randrange(2, p - 1)
    h = pow(g, s, p)
    print(f"PARAM_P={p}")
    print(f"PARAM_G={g}")
    print(f"PARAM_H={h}")
    print(f"ORACLE_S={s}")


if __name__ == "__main__":
    main()
