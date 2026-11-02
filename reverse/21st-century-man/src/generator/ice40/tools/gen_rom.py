#!/usr/bin/env python3
"""
gen_rom.py -- turn a model JSON written by `text_lemniscate build --model`
into the fixed-point tables of the iCE40 evaluator, plus test vectors.

    g(z) = prod_j (z - a_j) / ( c * prod_k (z - b_k)^m_k )

The iCE40 design keeps every coordinate as a signed Q4.28 fixed-point number
(range [-8, 8), resolution 2^-28) and every running product as a complex
block-floating-point number (Q2.30 mantissas, shared binary exponent).

Outputs (in --out, default gen/)
  rom.hex      block-RAM image: one 32-bit word {im, re} (Q4.12 hex, i.e. the
               top 16 bits of the Q4.28 coordinate) per zero, followed by one
               per pole (words N_ZEROS .. N_ZEROS + N_POLES - 1); the model
               must be quantised first (tools/scale_model.py)
  orders.vh    the pole orders as a Verilog case statement on pole_idx
  params.vh    N_ZEROS, N_POLES, C_MANT_INV (Q2.30 of 1/c mantissa), C_EXP
  vectors.txt  "x_hex y_hex log2|g| inside" per line, x/y as fp32 bit patterns,
               log2|g| in double precision from the SAME Q4.28-rounded inputs
               and coefficients, so the testbench measures only the hardware's
               arithmetic error. Exact zeros/poles are written as -1e300/1e300.

usage: python3 tools/gen_rom.py ../dsp58/model/hello.json [--out gen] [--vectors 3000]
"""
import argparse
import json
import math
import os
import struct

import numpy as np

FRAC = 28                    # Q4.28 for coordinates
LIM = 4.0                    # inputs are saturated to [-4, 4) by the hardware


def to_q428(v):
    """coefficient as stored in the ROM: fp32-rounded, then converted exactly like
    the hardware converts its fp32 inputs, so that sending a zero's fp32
    coordinates hits it exactly. Returns (int, exact float value)."""
    q = sat_q428_from_f32(v)
    return q, q / 2**FRAC


def hex32(q):
    return "%08x" % (q & 0xFFFFFFFF)


def hex16(q):
    return "%04x" % (q & 0xFFFF)


def f32_bits(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def f32_round(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


def sat_q428_from_f32(v):
    """what the hardware's fp32 -> Q4.28 converter produces (truncation toward zero)"""
    v = f32_round(v)
    if v >= LIM:
        return 2**31 - 1
    if v < -LIM:
        return -(2**31)
    s = -1 if v < 0 else 1
    return s * int(abs(v) * 2**FRAC)   # truncate the magnitude, as the shifter does


def reference(zq, aq, bq, orders, log_c):
    """log2|g| in double for Q4.28 points zq against Q4.28 coefficients"""
    out = []
    for z in zq:
        d = z - aq
        if np.any(d == 0):
            out.append(-1e300)
            continue
        s = np.log(np.abs(d)).sum()
        e = z - bq
        if np.any(e == 0):
            out.append(1e300)
            continue
        s -= (orders * np.log(np.abs(e))).sum()
        out.append((s - log_c) / math.log(2))
    return np.array(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "gen"))
    ap.add_argument("--vectors", type=int, default=3000)
    a = ap.parse_args()
    d = json.load(open(a.model))

    zeros = [complex(*p) for p in d["zeros"]]
    poles = [complex(*p) for p in d["poles"]]
    orders = [int(m) for m in d["pole_orders"]]
    assert all(1 <= m <= 255 for m in orders), "pole orders must fit in a byte"
    assert len(poles) <= 1023, "pole index is 10 bits wide"
    log_c = float(d["log_c"])
    l2 = log_c / math.log(2)
    c_exp = math.floor(l2)
    c_mant_inv = 2.0 ** (c_exp - l2)             # 1/c = c_mant_inv * 2^-c_exp, in (0.5, 1]
    c_mant_q = int(round(c_mant_inv * 2**30))    # Q2.30
    reg = d["region"]
    if "box" in reg:
        x0, y0, x1, y1 = reg["box"]
    else:
        cx, cy, r = reg["circle"]
        x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r
    assert max(abs(x0), abs(x1), abs(y0), abs(y1)) < LIM, "region must lie in [-4, 4)"

    os.makedirs(a.out, exist_ok=True)

    # ---- coefficient ROM: zeros, then poles ---------------------------------
    zr = [to_q428(z.real) for z in zeros]
    zi = [to_q428(z.imag) for z in zeros]
    pr = [to_q428(p.real) for p in poles]
    pi = [to_q428(p.imag) for p in poles]
    # the ROM holds the top 16 bits (Q4.12) of each coordinate: the model must
    # already be quantised (tools/scale_model.py), else the low bits would be lost
    with open(os.path.join(a.out, "rom.hex"), "w") as f:
        for (qr, _), (qi, _) in list(zip(zr, zi)) + list(zip(pr, pi)):
            assert qr & 0xFFFF == 0 and qi & 0xFFFF == 0, \
                "coefficients must be multiples of 2^-12: run tools/scale_model.py first"
            f.write(hex16(qi >> 16) + hex16(qr >> 16) + "\n")

    # ---- pole orders ----------------------------------------------------------
    with open(os.path.join(a.out, "orders.vh"), "w") as f:
        f.write(f"// Generated by tools/gen_rom.py from {os.path.basename(a.model)} -- do not edit.\n")
        f.write("// pole_order = multiplicity of pole pole_idx (ROM word N_ZEROS + pole_idx)\n")
        f.write("always @* begin\n    case (pole_idx)\n")
        for k, m in enumerate(orders):
            f.write(f"        {k}: pole_order = 8'd{m};\n")
        f.write("        default: pole_order = 8'd1;\n")
        f.write("    endcase\nend\n")

    # ---- parameters ------------------------------------------------------------
    with open(os.path.join(a.out, "params.vh"), "w") as f:
        f.write(f"""// Generated by tools/gen_rom.py from {os.path.basename(a.model)} -- do not edit.
// text: {d.get('text', '')!r}, region: {reg}
// g(z) = prod_j (z - a_j) / ( c * prod_k (z - b_k)^m_k ),  1/c = C_MANT_INV * 2^-C_EXP
localparam integer N_ZEROS    = {len(zeros)};
localparam integer N_POLES    = {len(poles)};
localparam integer N_DEN      = {sum(orders)};
localparam integer C_EXP      = {c_exp};
localparam [31:0]  C_MANT_INV = 32'h{hex32(c_mant_q)};   // Q2.30 of {c_mant_inv!r}
""")

    # ---- test vectors ---------------------------------------------------------
    rng = np.random.default_rng(1)
    ol = d["outline"]
    if ol and isinstance(ol[0][0], list):          # several closed curves (holes kept)
        ol = [p for ring in ol for p in ring]
    outline = np.array([complex(*p) for p in ol])
    n = a.vectors
    gx, gy = np.meshgrid(np.linspace(x0, x1, 60), np.linspace(y0, y1, 20))
    grid = (gx + 1j * gy).ravel()
    rand = x0 + (x1 - x0) * rng.uniform(size=n // 3) + 1j * (y0 + (y1 - y0) * rng.uniform(size=n // 3))
    k = rng.choice(len(outline), n // 6)
    t = outline[(k + 1) % len(outline)] - outline[k - 1]
    nrm = -1j * t / np.abs(t)
    near = np.r_[outline[k] + 2e-3 * nrm, outline[k] - 2e-3 * nrm]
    special = np.array([zeros[0], poles[0] if poles else zeros[1]])
    pts = np.r_[special, grid, rand, near][:max(n, 2)]

    x32 = [f32_round(p.real) for p in pts]
    y32 = [f32_round(p.imag) for p in pts]
    zq = np.array([sat_q428_from_f32(x) / 2**FRAC + 1j * sat_q428_from_f32(y) / 2**FRAC
                   for x, y in zip(x32, y32)])
    aq = np.array([r[1] + 1j * i[1] for r, i in zip(zr, zi)])
    bq = np.array([r[1] + 1j * i[1] for r, i in zip(pr, pi)])
    l2abs = reference(zq, aq, bq, np.array(orders, dtype=float), log_c)
    with open(os.path.join(a.out, "vectors.txt"), "w") as f:
        for x, y, l in zip(x32, y32, l2abs):
            f.write(f"{f32_bits(x):08x} {f32_bits(y):08x} {l:.17g} {1 if l < 0 else 0}\n")

    inside = int((l2abs < 0).sum())
    print(f"rom.hex: {len(zeros)} zeros + {len(poles)} poles ({sum(orders)} denominator factors); "
          f"1/c = {c_mant_inv:.9f} * 2^-{c_exp}")
    print(f"vectors.txt: {len(x32)} points ({inside} inside, 1 exact zero, 1 exact pole)")


if __name__ == "__main__":
    main()
