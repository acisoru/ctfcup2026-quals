#!/usr/bin/env python3
"""
scale_model.py -- fit a text_lemniscate model into the evaluator's coordinate
range and quantise its coefficients to what the ROM stores.

The iCE40 evaluator saturates inputs to [-4, 4) (Q4.28) and keeps every zero and
pole as a 16-bit Q4.12 number (multiples of 2^-12). A long text comes out of
text_lemniscate tens of font units wide, so it is scaled and centred first:

    z' = s * (z - z_c)        s = min(2*lim / width, 2*lim / height)

g is invariant up to its level:  for g(z) = prod (z - a_j) / (c prod (z - b_k)^m_k)
the function of z' has zeros s(a_j - z_c), poles s(b_k - z_c) and
log c' = log c + (N - M) log s,  N = number of zeros, M = sum of pole orders.
Zeros and poles are then rounded to multiples of 2^-12. That moves the outline
|g| = 1 by a fraction of the rounding step only (the level sits e^-offset below
the letters), and makes the JSON model the exact function the hardware computes.

usage: python3 tools/scale_model.py in.json out.json [--lim 3.9] [--frac 12]
"""
import argparse
import json
import math

import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--lim", type=float, default=3.9, help="the region is fitted into [-lim, lim]^2")
    ap.add_argument("--frac", type=int, default=12, help="fraction bits of the stored coefficients")
    a = ap.parse_args()
    d = json.load(open(a.inp))

    reg = d["region"]
    if "box" in reg:
        x0, y0, x1, y1 = reg["box"]
    else:
        cx, cy, r = reg["circle"]
        x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r
    zc = complex((x0 + x1) / 2, (y0 + y1) / 2)
    s = min(2 * a.lim / (x1 - x0), 2 * a.lim / (y1 - y0))
    step = 2.0 ** -a.frac

    def tr(p):
        z = s * (complex(*p) - zc)
        return [z.real, z.imag]

    def trq(p):
        z = s * (complex(*p) - zc)
        return [round(z.real / step) * step, round(z.imag / step) * step]

    zeros = [trq(p) for p in d["zeros"]]
    poles = [trq(p) for p in d["poles"]]
    orders = [int(m) for m in d["pole_orders"]]
    n, m = len(zeros), sum(orders)
    log_c = float(d["log_c"]) + (n - m) * math.log(s)

    out = {
        "description": d.get("description", "").split(" 'disk_map'")[0]
        + f" Scaled by {s!r} about {[zc.real, zc.imag]!r} and quantised to multiples of 2^-{a.frac} by scale_model.py.",
        "text": d.get("text", ""),
        "degree": d.get("degree", n),
        "zeros": zeros,
        "poles": poles,
        "pole_orders": orders,
        "log_c": log_c,
        "clearance": float(d.get("clearance", 0.0)) * s,
        "region": {"box": [s * (x0 - zc.real), s * (y0 - zc.imag), s * (x1 - zc.real), s * (y1 - zc.imag)]},
        "scale": {"s": s, "center": [zc.real, zc.imag], "frac": a.frac},
    }
    def tr_curves(c):          # a list of points, or (holes kept) a list of such lists
        if c and isinstance(c[0][0], list):
            return [tr_curves(r) for r in c]
        return [tr(p) for p in c]

    for key in ("polygon", "outline"):
        if key in d:
            out[key] = tr_curves(d[key])

    # region check of the quantised function: |g| > 1 on the whole edge of the box
    bx0, by0, bx1, by1 = out["region"]["box"]
    t = np.linspace(0, 1, 2000)
    edge = np.r_[bx0 + (bx1 - bx0) * t + 1j * by0, bx0 + (bx1 - bx0) * t + 1j * by1,
                 bx0 + 1j * (by0 + (by1 - by0) * t), bx1 + 1j * (by0 + (by1 - by0) * t)]
    az = np.array([complex(*p) for p in zeros])
    bz = np.array([complex(*p) for p in poles])
    om = np.array(orders, dtype=float)
    la = np.log(np.abs(edge[:, None] - az[None, :])).sum(1) - (om * np.log(np.abs(edge[:, None] - bz[None, :]))).sum(1) - log_c
    out["region_report"] = {"min_log_abs_on_edge": float(la.min()), "text_inside_region": bool(la.min() > 0)}

    json.dump(out, open(a.out, "w"))
    print(f"scale {s:.6g}, centre ({zc.real:.4g}, {zc.imag:.4g}); box {[round(v, 4) for v in out['region']['box']]}; "
          f"{n} zeros, {len(poles)} poles (order {m}); log c = {log_c:.4f}; min log|g| on the edge = {la.min():.3f}")


if __name__ == "__main__":
    main()
