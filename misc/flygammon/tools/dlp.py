#!/usr/bin/env python3
"""Self-contained discrete-log toolkit for flygammon.

No third-party dependencies. Provides:
  - Miller-Rabin primality
  - Pollard-rho factorization
  - smooth-prime generation (p-1 squarefree, controlled factor size)
  - primitive-root search
  - Baby-Step/Giant-Step in a prime-order subgroup
  - Pohlig-Hellman + CRT discrete log over a smooth group

This same module is what the reference solver uses to recover the oracle secret
`s` from the public key `h = g^s mod p` — the intended break.
"""

import random


# --------------------------------------------------------------------- primality

_SMALL_PRIMES = [
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71,
    73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151,
]


def is_prime(n: int, rounds: int = 40) -> bool:
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n == p:
            return True
        if n % p == 0:
            return False
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def gen_prime(bits: int) -> int:
    while True:
        n = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        if is_prime(n):
            return n


# ----------------------------------------------------------------- factorization

def _pollard_rho(n: int) -> int:
    if n % 2 == 0:
        return 2
    while True:
        x = random.randrange(2, n)
        y = x
        c = random.randrange(1, n)
        d = 1
        while d == 1:
            x = (x * x + c) % n
            y = (y * y + c) % n
            y = (y * y + c) % n
            d = _gcd(abs(x - y), n)
        if d != n:
            return d


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def factorize(n: int) -> dict:
    """Return {prime: exponent}."""
    factors = {}
    stack = [n]
    while stack:
        m = stack.pop()
        if m == 1:
            continue
        if is_prime(m):
            factors[m] = factors.get(m, 0) + 1
            continue
        d = _pollard_rho(m)
        stack.append(d)
        stack.append(m // d)
    return factors


# --------------------------------------------------------- smooth-prime generation

def gen_smooth_prime(total_bits: int, factor_bits: int, seed=None):
    """Generate a prime p with p-1 = 2 * q1 * ... * qk (distinct odd primes, each
    ~factor_bits) and p ~ total_bits. Returns (p, factorization_of_p_minus_1).

    Squarefree p-1 keeps Pohlig-Hellman simple (no prime-power lifting) and the
    largest factor ~factor_bits sets the BSGS cost (~2^(factor_bits/2))."""
    rng = random.Random(seed) if seed is not None else random
    while True:
        qs = [2]
        prod = 2
        used = set()
        # Multiply distinct ~factor_bits primes until just under total_bits.
        while prod.bit_length() < total_bits - factor_bits:
            q = _rand_prime(factor_bits, rng)
            if q in used:
                continue
            used.add(q)
            qs.append(q)
            prod *= q
        # Final factor to reach ~total_bits.
        remaining = total_bits - prod.bit_length()
        if remaining < 16:
            continue
        q = _rand_prime(remaining, rng)
        if q in used:
            continue
        qs.append(q)
        prod *= q
        p = prod + 1
        if p.bit_length() == total_bits and is_prime(p):
            fac = {}
            for q in qs:
                fac[q] = fac.get(q, 0) + 1
            if all(e == 1 for e in fac.values()):  # squarefree
                return p, fac


def _rand_prime(bits, rng):
    while True:
        n = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if is_prime(n):
            return n


# ------------------------------------------------------------- primitive root

def primitive_root(p: int, fac_p_minus_1: dict) -> int:
    order = p - 1
    primes = list(fac_p_minus_1.keys())
    for g in range(2, p):
        if all(pow(g, order // r, p) != 1 for r in primes):
            return g
    raise RuntimeError("no primitive root found")


# ----------------------------------------------------------- discrete log

def bsgs(g: int, h: int, p: int, order: int) -> int:
    """Smallest x in [0, order) with g^x == h (mod p), g of the given order."""
    m = 1
    while m * m < order:
        m += 1
    table = {}
    e = 1
    for j in range(m):
        table.setdefault(e, j)
        e = e * g % p
    g_inv_m = pow(pow(g, m, p), -1, p)
    gamma = h
    for i in range(m + 1):
        if gamma in table:
            return i * m + table[gamma]
        gamma = gamma * g_inv_m % p
    raise RuntimeError("bsgs: no solution (bad order?)")


def pohlig_hellman(g: int, h: int, p: int, fac_p_minus_1: dict) -> int:
    """Recover x with g^x == h (mod p) over a smooth, squarefree group order."""
    order = p - 1
    residues = []
    moduli = []
    for r, e in fac_p_minus_1.items():
        assert e == 1, "this implementation assumes squarefree p-1"
        cof = order // r
        gr = pow(g, cof, p)  # element of order r
        hr = pow(h, cof, p)
        xr = bsgs(gr, hr, p, r)
        residues.append(xr)
        moduli.append(r)
    return _crt(residues, moduli)


def _crt(residues, moduli):
    x = 0
    M = 1
    for m in moduli:
        M *= m
    for r, m in zip(residues, moduli):
        Mi = M // m
        x += r * Mi * pow(Mi, -1, m)
    return x % M


def discrete_log(g: int, h: int, p: int, fac_p_minus_1: dict = None) -> int:
    if fac_p_minus_1 is None:
        fac_p_minus_1 = factorize(p - 1)
    return pohlig_hellman(g, h, p, fac_p_minus_1)
