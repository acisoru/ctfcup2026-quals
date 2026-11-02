import itertools
from fpylll import IntegerMatrix, LLL, CVP

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

def solve_cvp(A, p, n, centers, C=2**20):
    candidates = set()

    M = Matrix(ZZ, n+1, n+1)
    for i in range(n):
        M[i, i] = 1
        M[i, n] = pow(256, i, p) * C
    M[n, n] = p * C

    B = IntegerMatrix.from_matrix(M)
    LLL.reduction(B)

    for c in centers:
        target = [c] * n + [A * C]
        
        try:
            v = CVP.closest_vector(B, target)
        except Exception:
            continue
        
        s = [ZZ(v[i]) for i in range(n)]
        candidates.add(tuple(s))

    return list(candidates)

def reconstruct_flags(p, j, n, k):
    l = n - 8
    known = b"ctfcup{" + b"\x00"*l + b"}"
    known = int.from_bytes(known, 'little')

    j = (j - known) / 256^7

    flags = []

    for prefix in itertools.product(range(32, 128), repeat = k):
        A = j - sum(c * 256^i for i, c in enumerate(prefix))
        A = ZZ((A / 256^k) % p)

        for center in range(32, 128, 8):
            for x in solve_cvp(A, p, l - k, centers=[center]):
                if all(32 <= y <= 127 for y in x):
                    flag = b'ctfcup{' + bytes(prefix) + bytes(x) + b'}'
                    flags.append(flag)

    return flags

def main():
    P.<x> = PolynomialRing(QQ)

    n = 27
    k = 1

    # x^3 + 6079433314242371108270239373533376748*x - 1779744368654530162000920720207404089
    a = 6079433314242371108270239373533376748
    b = -1779744368654530162000920720207404089
    j2 = EllipticCurve(QQ, [a, b]).j_invariant()

    p = 78390170948882985413083708539615087041

    # for flag in reconstruct_flags(p, ZZ(j2 % p), n, k):
    #     print(flag)

    H = Phi_power(2)(x, j2).change_ring(GF(p))

    for j1, _ in H.roots():
        for flag in reconstruct_flags(p, ZZ(j1), n, k):
            print(flag)

if __name__ == '__main__':
    main()
