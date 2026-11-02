#!/usr/bin/env sage

def Phi_power(m):
    assert m >= 1

    R_base.<X, Y> = PolynomialRing(ZZ, 2)
    Phi_2_base = classical_modular_polynomial(2)

    if m == 1:
        return R_base(Phi_2_base)

    R3.<X, Y, Z> = PolynomialRing(ZZ, 3)
    Phi_2_ZY = R3(Phi_2_base(X=Z, Y=Y))

    Phi_current_XZ = R3(Phi_2_base(X=X, Y=Z))

    for i in range(2, m + 1):
        target_degree = 3 * 2**(i - 1)

        res = Phi_current_XZ.resultant(Phi_2_ZY, Z)
        factors = res.factor()

        Phi_next = None
        for f, mult in factors:
            if f.degree(X) == target_degree:
                Phi_next = f
                break

        if Phi_next is None:
            raise RuntimeError()

        if i < m:
            Phi_current_XZ = R3(Phi_next(Y=Z))
        else:
            Phi_current_XZ = Phi_next

    return R_base(Phi_current_XZ)

def main():
    R.<X, Y> = PolynomialRing(ZZ)

    H = [
        R(X - Y),
        R(Phi_power(1)),
        R(Phi_power(2)),
        R(Phi_power(3)),
        R(Phi_power(4)),
    ]

    count = 0
    results = [0] * 5

    while count < 200:
        try:
            p = next_prime(getrandbits(128))
            E1 = EllipticCurve(GF(p), j = randrange(p))
            E2 = E1

            for _ in range(64):
                E2 = choice(E2.isogenies_prime_degree(2)).codomain()
        except Exception:
            continue

        j1 = ZZ(E1.j_invariant())
        j2 = ZZ(E2.j_invariant())

        for k in range(5):
            if H[k](j1, j2) % p == 0:
                results[k] += 1

        count += 1

    for k in range(5):
        ratio = float(results[k] / count)
        print(f'k = {k}: {ratio * 100:.2f}%')

if __name__ == '__main__':
    main()
