using Oscar

function Phi_power(m)
    @assert m >= 1

    R_base, (X, Y) = polynomial_ring(ZZ, ["X", "Y"])
    Phi_2_base = classical_modular_polynomial(R_base, 2)

    if m == 1
        return Phi_2_base
    end

    R3, (X3, Y3, Z3) = polynomial_ring(ZZ, ["X", "Y", "Z"])
    Phi_2_ZY = hom(R_base, R3, [Z3, Y3])(Phi_2_base)
    Phi_current_XZ = hom(R_base, R3, [X3, Z3])(Phi_2_base)

    for i in 2:m
        target_degree = 3 * 2^(i - 1)

        res = resultant(Phi_current_XZ, Phi_2_ZY, 3)
        factors = factor(res)

        Phi_next = nothing
        for (f, mult) in factors
            if degree(f, 1) == target_degree
                Phi_next = f
                break
            end
        end

        if Phi_next === nothing
            error("unable to find factor of degree $(target_degree)")
        end

        if i < m
            Phi_current_XZ = hom(R3, R3, [X3, Z3, Z3])(Phi_next)
        else
            Phi_current_XZ = Phi_next
        end
    end

    return hom(R3, R_base, [X, Y, X])(Phi_current_XZ)
end

const ROOTS_CACHE = Dict{Any, Any}()
const CHILDREN_CACHE = Dict{Any, Any}()

function division_roots(E)
    key = (base_field(E), discriminant(E))
    if haskey(ROOTS_CACHE, key)
        return ROOTS_CACHE[key]
    end

    result = roots(division_polynomial_univariate(E, 2)[1])
    ROOTS_CACHE[key] = result
    return result
end

function isogeny_children(E)
    key = (base_field(E), discriminant(E))
    if haskey(CHILDREN_CACHE, key)
        return CHILDREN_CACHE[key]
    end

    K = base_field(E)
    a4, a6 = a_invariants(E)[4], a_invariants(E)[5]

    result = Any[]
    for root in division_roots(E)
        t = 3*root^2 + a4
        push!(result, elliptic_curve(K, [a4 - 5*t, a6 - 7*root*t]))
    end

    CHILDREN_CACHE[key] = result
    return result
end

function build_bfs(E0, max_depth)
    order = Tuple{Any, Any, Int}[]
    push!(order, (j_invariant(E0), E0, 0))

    level = Any[E0]
    for d in 1:max_depth
        next_level = Any[]
        for E in level
            for F in isogeny_children(E)
                push!(next_level, F)
                push!(order, (j_invariant(F), F, d))
            end
        end
        level = next_level
    end

    map = Dict{Any, Vector{Tuple{Any, Int}}}()
    for (j, E, d) in order
        push!(get!(map, j, Tuple{Any, Int}[]), (E, d))
    end

    return order, map
end

function solve(a, b, k, count)
    P, x = polynomial_ring(QQ, "x")

    pol = x^3 + a*x + b

    E = elliptic_curve(QQ, [QQ(coeff(pol, 1)), QQ(coeff(pol, 0))])
    j = j_invariant(E)

    println("k = $(k)")

    if k == 0
        K, _ = number_field(pol)
        Y = K(j)
    else
        Phi = Phi_power(k)
        H = hom(parent(Phi), P, [x, P(j)])(Phi)
        K, Y = number_field(H)
    end

    d = BigInt(-2)^(count - k)

    E1 = elliptic_curve(K, [-3*Y*(Y - 1728), -2*Y*(Y - 1728)^2])
    E2 = elliptic_curve(K, [K(QQ(coeff(pol, 1))) / K(d)^2, K(QQ(coeff(pol, 0))) / K(d)^3])

    max_depth = div(k, 2) + 1

    left_order, left_map = build_bfs(E1, max_depth)
    right_order, right_map = build_bfs(E2, max_depth)

    Ns = Vector{ZZRingElem}()

    for (j_left, E_left, i_left) in left_order
        if !haskey(right_map, j_left)
            continue
        end

        for (E_right, i_right) in right_map[j_left]
            if j_invariant(E_left) != j_invariant(E_right)
                continue
            end

            power = k + i_right - i_left
            for root_left in division_roots(E_left)
                for root_right in division_roots(E_right)
                    N_i = numerator(norm(root_left * (-2)^power - root_right))
                    push!(Ns, N_i)
                end
            end
        end
    end

    gs = Set{ZZRingElem}()

    for N1 in Ns
        for N2 in Ns
            if N1 == N2
                continue
            end

            push!(gs, gcd(N1, N2))
        end
    end

    for g in gs
        bits = ndigits(g, base=2)
        println("  g = $(g) ($(bits) bits)")
    end
end

function main()
    count = 64

    # x^3 + 6079433314242371108270239373533376748*x - 1779744368654530162000920720207404089
    a = parse(BigInt, "6079433314242371108270239373533376748")
    b = parse(BigInt, "-1779744368654530162000920720207404089")

    for k in [0, 2]
        solve(a, b, k, count)
    end
end

main()
