#!/usr/bin/env python3
"""
solve.py -- read the flag out of the iCE40 bitstream without running it.

    iceunpack g.bin g.asc
    icebox_vlog -s -n chip -p pins.pcf g.asc > g.v        # pcf: clk 35, uart_rxd 6, uart_txd 9
    python3 solve.py g.v flag.png                          # needs numpy, scipy, pillow
    python3 solve.py g.v flag.png --port /dev/ttyUSB0      # + pyserial: also the exact |g| < 1

The evaluator keeps its coefficients (the zeros and poles of g) in block RAM:
one 32-bit word {im, re} per point, both signed Q4.12, 13 groups of 256 words,
each group = two SB_RAM40_4K in 256 x 16 mode (READ_MODE 0): one holds re, the
other im. Inside a BRAM the 16 bits of a word are stored in the physical column
order of the iCE40, which is the bit-reversed index: logical bit p sits at
INIT bit position rev4(p) (0->0, 1->8, 2->4, ...). The address order is kept.

All 26 BRAMs share the address and enable nets; a word's group is selected by
an output mux that ABC has rewritten beyond easy recognition, so which re-BRAM
goes with which im-BRAM is recovered from the data instead: the zeros lie on
the outline of the letters a few thousandths apart, so with the right pairing
most points have a very close neighbour, while a wrong pairing scatters 256
points over the strip. Pairs are chosen by hill climbing on the number of
points whose nearest neighbour is closer than ~1/60 of the strip height.
(re and im are told apart by size: |im| < 0.13, so its high bits are a sign
extension.)

Plotting the points gives the text: the zeros trace the letters just inside
their outline, the poles sit in the counters (flag_points.png); the local
density of points (flag.png) is easier to read, since inside a stroke both of
its edges contribute. With --port the device itself is used to finish the job:
asked exactly at an isolated point it answers with the ZERO or POLE flag, and a
few hundred random queries give log|g|, from which the pole orders and the
level c follow by least squares; flag_exact.png is then |g| < 1 itself.
"""
import re
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

REV4 = [int(f"{i:04b}"[::-1], 2) for i in range(16)]


def parse_brams(verilog):
    """-> list of (name, read_mode, [256 x 16-bit words], rdata nets msb..lsb)"""
    out = []
    for params, name, conn in re.findall(r'SB_RAM40_4K\s*#\((.*?)\)\s*(\w+)\s*\((.*?)\);', verilog, re.S):
        rm = int(re.search(r'READ_MODE\((\d)\)', params).group(1))
        init = {int(k, 16): int(v, 16) for k, v in re.findall(r"INIT_([0-9A-F])\(256'h([0-9a-fA-F]+)\)", params)}
        bits = 0
        for k in range(16):
            bits |= init.get(k, 0) << (256 * k)
        raw = [(bits >> (16 * i)) & 0xFFFF for i in range(256)]
        words = [sum(((w >> REV4[p]) & 1) << p for p in range(16)) for w in raw]
        rdata = re.search(r'\.RDATA\(\{(.*?)\}\)', conn, re.S).group(1).replace(' ', '').split(',')
        out.append((name, rm, words, rdata))
    return out


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def main():
    src, png = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "flag.png")
    roms = [(n, w) for n, rm, w, _ in parse_brams(open(src).read()) if rm == 0 and any(w)]
    print(f"{len(roms)} ROM block RAMs")

    def is_im(words):
        return sum(all(((w >> k) & 1) == ((w >> 15) & 1) for k in range(10, 15)) for w in words) > 0.9 * len(words)
    ims = [r for r in roms if is_im(r[1])]
    res = [r for r in roms if not is_im(r[1])]
    print(f"  {len(res)} hold re, {len(ims)} hold im")
    assert len(ims) == len(res)
    R = np.array([[s16(w) / 4096.0 for w in r[1]] for r in res])
    I = np.array([[s16(w) / 4096.0 for w in r[1]] for r in ims])
    close = (I.max() - I.min()) / 60

    def points(perm):
        pts = np.stack([R.ravel(), I[perm].ravel()], 1)
        return pts[np.all(pts != 0, axis=1)]           # the unused tail of the last group

    def cost(perm):
        pts = points(perm)
        d, _ = cKDTree(pts).query(pts, k=2)
        return -int((d[:, 1] < close).sum())

    n = len(res)
    rng = np.random.default_rng(0)
    best_p, best_c = None, 1
    for _ in range(3):
        p = rng.permutation(n)
        c = cost(p)
        improved = True
        while improved:
            improved = False
            for a in range(n):
                for b in range(a + 1, n):
                    q = p.copy()
                    q[a], q[b] = q[b], q[a]
                    cq = cost(q)
                    if cq < c:
                        p, c, improved = q, cq, True
        print(f"  pairing: {-c} points with a neighbour closer than {close:.4f}")
        if c < best_c:
            best_p, best_c = p, c
    for a in range(n):
        print(f"  {res[a][0]:>12} (re) + {ims[best_p[a]][0]:<12} (im)")

    pts = points(best_p)
    print(f"{len(pts)} points, x in [{pts[:, 0].min():.3f}, {pts[:, 0].max():.3f}], "
          f"y in [{pts[:, 1].min():.3f}, {pts[:, 1].max():.3f}]")
    np.savetxt("points.csv", pts, delimiter=",", fmt="%.6f")

    # ---- pictures without the device: the points, and the local density of points
    # (inside a stroke both edges contribute, outside only one)
    W = 2400
    x0, x1 = pts[:, 0].min() - 0.03, pts[:, 0].max() + 0.03
    y0, y1 = pts[:, 1].min() - 0.03, pts[:, 1].max() + 0.03
    H = int(W * (y1 - y0) / (x1 - x0))
    sx, sy = W / (x1 - x0), H / (y1 - y0)
    img = Image.new("L", (W, H), 255)
    dr = ImageDraw.Draw(img)
    for x, y in pts:
        px, py = (x - x0) * sx, (y1 - y) * sy
        dr.ellipse([px - 1.5, py - 1.5, px + 1.5, py + 1.5], fill=0)
    img.save(png.replace(".png", "_points.png"))
    xs, ys = np.linspace(x0, x1, W), np.linspace(y1, y0, H)
    gx, gy = np.meshgrid(xs, ys)
    tree = cKDTree(pts)
    dens = np.array([len(l) for l in tree.query_ball_point(np.stack([gx.ravel(), gy.ravel()], 1), 6 * close)])
    dens = dens.reshape(H, W) / np.percentile(dens, 97)
    Image.fromarray((255 - 255 * np.clip(dens, 0, 1)).astype(np.uint8)).save(png)
    print(f"wrote {png} (density) and {png.replace('.png', '_points.png')} ({W}x{H}), points.csv")

    # ---- with the device: which points are poles, their orders and the level c, then |g| < 1 exactly
    if "--port" not in sys.argv:
        return
    port = sys.argv[sys.argv.index("--port") + 1]
    dev = Device(port)
    d, _ = tree.query(pts, k=2)
    cand = np.where(d[:, 1] > 3 * close)[0]          # poles are isolated; zeros mostly are not
    print(f"asking the device at the {len(cand)} isolated points to tell poles from zeros ...")
    kind = np.ones(len(pts), int)                       # +1: zero
    for n, i in enumerate(cand):
        f = dev.query(*pts[i])["flags"]
        if f & 0x02:
            kind[i] = -1
        elif not f & 0x04:
            print(f"  point {i} {pts[i]} is neither a zero nor a pole?! flags {f:#x}")
        if n % 50 == 49:
            print(f"  {n + 1}/{len(cand)}, {int((kind == -1).sum())} poles so far")
    poles = np.where(kind == -1)[0]
    zeros = np.where(kind == 1)[0]
    print(f"  {len(zeros)} zeros, {len(poles)} poles")

    # log|g(z)| = sum log|z - a_j| - sum m_k log|z - b_k| - log c  ->  least squares for m_k, log c
    n = len(poles) + 60
    rng = np.random.default_rng(1)
    q = np.stack([rng.uniform(pts[:, 0].min(), pts[:, 0].max(), n), rng.uniform(pts[:, 1].min(), pts[:, 1].max(), n)], 1)
    print(f"asking the device at {n} random points for the pole orders and the level ...")
    rows, rhs = [], []
    for i, (x, y) in enumerate(q):
        r = dev.query(x, y)
        if not np.isfinite(r["log2abs"]):
            continue
        z = complex(x, y)
        za = np.log(np.abs(z - (pts[zeros, 0] + 1j * pts[zeros, 1]))).sum()
        zb = np.log(np.abs(z - (pts[poles, 0] + 1j * pts[poles, 1])))
        rows.append(np.r_[-zb, -1.0])
        rhs.append(r["log2abs"] * np.log(2) - za)
        if i % 50 == 49:
            print(f"  {i + 1}/{n}")
    sol, *_ = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)
    orders = np.rint(sol[:-1]).astype(int)
    print(f"  pole orders {orders.min()}..{orders.max()} (max rounding error {np.abs(sol[:-1] - orders).max():.3f}), "
          f"log c = {sol[-1]:.3f}")
    res = np.array(rhs) - np.array(rows) @ np.r_[orders, sol[-1]]
    log_c = sol[-1] + res.mean()

    a = pts[zeros, 0] + 1j * pts[zeros, 1]
    b = pts[poles, 0] + 1j * pts[poles, 1]
    ink = np.empty((H, W), bool)
    for i, y in enumerate(ys):
        z = xs + 1j * y
        la = np.log(np.abs(z[:, None] - a[None, :])).sum(1) - (orders * np.log(np.abs(z[:, None] - b[None, :]))).sum(1) - log_c
        ink[i] = la < 0
    Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).save(png.replace(".png", "_exact.png"))
    print(f"wrote {png.replace('.png', '_exact.png')}: |g| < 1 of the recovered function")


class Device:
    """the UART protocol: A5 x y xor -> 5A re im e flags xor"""

    def __init__(self, port, baud=921600, timeout=60):
        import serial
        self.ser = serial.Serial(port, baud, timeout=timeout)

    def query(self, x, y):
        import math
        import struct
        payload = struct.pack("<ff", x, y)
        chk = 0
        for c in payload:
            chk ^= c
        self.ser.write(bytes([0xA5]) + payload + bytes([chk]))
        while True:
            h = self.ser.read(1)
            if not h:
                raise TimeoutError("no reply")
            if h[0] == 0x5A:
                break
        body = self.ser.read(14)
        re_, im, e, flags = struct.unpack("<ffiB", body[:13])
        if flags & 0x06 or not (math.isfinite(re_) and math.isfinite(im)):
            l2 = math.inf if flags & 0x02 else -math.inf
        else:
            l2 = e + 0.5 * math.log2(re_ * re_ + im * im)
        return dict(flags=flags, log2abs=l2)


if __name__ == "__main__":
    main()
