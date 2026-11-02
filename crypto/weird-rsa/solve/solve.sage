#!/usr/bin/env sage
#
# Polynomial RSA is broken because factoring a polynomial over a finite
# field is *easy* (Cantor-Zassenhaus runs in polynomial time), unlike
# factoring integers. So we just factor N, recover the group order, invert
# the exponent, and decrypt.

import ast

data = {}
with open('output.txt') as f:
    for line in f:
        k, _, v = line.partition('=')
        data[k.strip()] = ast.literal_eval(v.strip())

p = data['p']
e = data['e']
R.<x> = GF(p)[]
N = R(data['N'])
c = R(data['c'])

# factor the modulus -- trivial over GF(p)
factors = [f for f, _ in N.factor()]
print('factor degrees:', [f.degree() for f in factors])

# analogue of Euler's phi: number of units of GF(p)[x]/(N)
phi = prod(p**f.degree() - 1 for f in factors)

d = inverse_mod(e, phi)
m = power_mod(c, d, N)

flag = bytes(int(a) for a in m.list())
print(flag.decode())
