#!/usr/bin/env sage

with open('flag.txt', 'rb') as file:
    flag = file.read().strip()
    assert len(flag) == 27

p = next_prime(getrandbits(128))
E = EllipticCurve(GF(p), j = int.from_bytes(flag, 'little'))

for _ in range(64):
    E = choice(E.isogenies_prime_degree(2)).codomain()

print(x^3 + E.a4().lift_centered() * x + E.a6().lift_centered())
