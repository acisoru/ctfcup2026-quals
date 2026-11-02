#!/usr/bin/env sage
#
# Textbook RSA... but over polynomials instead of integers.
#
# We work in the ring R = GF(257)[x]. The modulus is a product of two
# "primes" (irreducible polynomials) N = P * Q, the public exponent is e,
# and a message polynomial m is encrypted as c = m^e mod N.
#
# The flag is encoded as the coefficients of m (constant term first).

p = 257
R.<x> = GF(p)[]
e = 65537

with open('flag.txt', 'rb') as f:
    flag = f.read().strip()

# message polynomial: flag bytes become coefficients m_0 + m_1*x + m_2*x^2 + ...
m = R([GF(p)(b) for b in flag])

while True:
    # two random irreducible polynomials -- the "primes" of our RSA
    P = R.irreducible_element(58, algorithm='random')
    Q = R.irreducible_element(59, algorithm='random')
    N = P * Q

    # number of units of R/(N), i.e. the analogue of Euler's phi for RSA
    phi = (p**P.degree() - 1) * (p**Q.degree() - 1)
    if gcd(e, phi) == 1:
        break

c = power_mod(m, e, N)

with open('output.txt', 'w') as f:
    f.write(f'p = {p}\n')
    f.write(f'e = {e}\n')
    f.write(f'N = {N.list()}\n')
    f.write(f'c = {c.list()}\n')
