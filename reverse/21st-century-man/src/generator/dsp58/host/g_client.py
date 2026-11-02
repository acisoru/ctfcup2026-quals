#!/usr/bin/env python3
"""
g_client.py -- talk to the Versal g(x, y) evaluator over UART (or to the
desktop emulator built by `make emulator`).

  request : 0xA5, x[fp32 LE], y[fp32 LE], xor of the 8 payload bytes
  reply   : 0x5A, re[fp32], im[fp32], e[int32], flags, xor of bytes 1..13
            g(x + iy) = (re + i im) * 2^e
            flags: 1 = |g| < 1 (inside the text), 2 = pole, 4 = zero, 0x80 = bad request

examples
  python3 g_client.py --port /dev/ttyUSB0 --at 0.3,0.4 --at 3,0.85
  python3 g_client.py --emulator ../build/g_uart_emulator --scan ../model/hello.json
  python3 g_client.py --port /dev/ttyUSB0 --check ../model/hello.json --n 300
"""
import argparse
import json
import math
import struct
import subprocess
import sys

SYNC_IN, SYNC_OUT = 0xA5, 0x5A
INSIDE, POLE, ZERO, BAD = 0x01, 0x02, 0x04, 0x80


class Device:
    def __init__(self, port=None, baud=115200, emulator=None, timeout=2.0):
        if emulator:
            self.proc = subprocess.Popen([emulator], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            self._write = lambda b: (self.proc.stdin.write(b), self.proc.stdin.flush())
            self._read = self.proc.stdout.read
        else:
            import serial  # pip install pyserial
            self.ser = serial.Serial(port, baud, timeout=timeout)
            self.ser.reset_input_buffer()
            self._write = self.ser.write
            self._read = self.ser.read

    def query(self, x, y):
        """returns dict(re, im, e, flags, log2abs, arg, inside)"""
        payload = struct.pack("<ff", x, y)
        chk = 0
        for b in payload:
            chk ^= b
        self._write(bytes([SYNC_IN]) + payload + bytes([chk]))
        # find the reply header, then read the rest
        while True:
            h = self._read(1)
            if not h:
                raise TimeoutError("no reply from the evaluator")
            if h[0] == SYNC_OUT:
                break
        body = self._read(14)
        if len(body) != 14:
            raise TimeoutError("short reply")
        ck = 0
        for b in body[:13]:
            ck ^= b
        if ck != body[13]:
            raise IOError("reply checksum error")
        re, im, e, flags = struct.unpack("<ffiB", body[:13])
        out = dict(re=re, im=im, e=e, flags=flags, inside=bool(flags & INSIDE))
        if flags & (POLE | ZERO | BAD) or not (math.isfinite(re) and math.isfinite(im)):
            out["log2abs"] = math.inf if flags & POLE else -math.inf
            out["arg"] = math.nan
        else:
            out["log2abs"] = e + 0.5 * math.log2(re * re + im * im)
            out["arg"] = math.atan2(im, re)
        return out


def value(r):
    """g as a Python complex (inf/0 when out of double range)"""
    if r["flags"] & POLE:
        return complex(math.inf, math.inf)
    try:
        s = math.ldexp(1.0, r["e"])
    except OverflowError:
        s = math.inf
    return complex(r["re"] * s, r["im"] * s)


def reference(model, x, y):
    """log2|g| at fp32-rounded (x, y) in double precision from the model JSON"""
    x = struct.unpack("<f", struct.pack("<f", x))[0]
    y = struct.unpack("<f", struct.pack("<f", y))[0]
    z = complex(x, y)
    s = 0.0
    for a in model["zeros"]:
        s += math.log(abs(z - complex(*a)))
    for b, m in zip(model["poles"], model["pole_orders"]):
        s -= m * math.log(abs(z - complex(*b)))
    return (s - model["log_c"]) / math.log(2)


def region_box(model):
    r = model["region"]
    if "box" in r:
        return r["box"]
    cx, cy, rad = r["circle"]
    return [cx - rad, cy - rad, cx + rad, cy + rad]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="serial port of the board, e.g. /dev/ttyUSB0 or COM5")
    src.add_argument("--emulator", help="path to build/g_uart_emulator")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--timeout", type=float, default=2.0, help="reply timeout in seconds (a simulated device needs ~10)")
    ap.add_argument("--at", action="append", default=[], help="point x,y (repeatable)")
    ap.add_argument("--scan", metavar="MODEL", help="ask the device for its inside flag on a grid over the model's region and draw it")
    ap.add_argument("--cols", type=int, default=100)
    ap.add_argument("--check", metavar="MODEL", help="compare random points with a double-precision reference")
    ap.add_argument("--n", type=int, default=200)
    a = ap.parse_args()
    dev = Device(a.port, a.baud, a.emulator, a.timeout)

    for s in a.at:
        x, y = (float(t) for t in s.split(","))
        r = dev.query(x, y)
        g = value(r)
        print(f"g({x}, {y}) = ({r['re']:.9g} {r['im']:+.9g}i) * 2^{r['e']}"
              f"   |g| = 2^{r['log2abs']:.6f}   arg = {r['arg']:.6f}   "
              f"{'inside' if r['inside'] else 'outside'}{'  POLE' if r['flags'] & POLE else ''}"
              f"{'  ZERO' if r['flags'] & ZERO else ''}   ~ {g:.6g}")

    if a.scan:
        model = json.load(open(a.scan))
        x0, y0, x1, y1 = region_box(model)
        cols = a.cols
        rows = max(4, int(cols * (y1 - y0) / (x1 - x0) * 0.5))   # terminal cells are ~2:1
        for i in range(rows):
            y = y1 - (i + 0.5) * (y1 - y0) / rows
            line = ""
            for j in range(cols):
                x = x0 + (j + 0.5) * (x1 - x0) / cols
                r = dev.query(x, y)
                line += "x" if r["flags"] & POLE else ("#" if r["inside"] else ".")
            print(line)
        print("# = |g| < 1 (smoothed text), . = |g| > 1, x = pole")

    if a.check:
        import random
        model = json.load(open(a.check))
        x0, y0, x1, y1 = region_box(model)
        rnd = random.Random(7)
        worst, flips = 0.0, 0
        for _ in range(a.n):
            x, y = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
            r = dev.query(x, y)
            ref = reference(model, x, y)
            if math.isfinite(r["log2abs"]):
                worst = max(worst, abs(r["log2abs"] - ref))
            if r["inside"] != (ref < 0):
                flips += 1
        print(f"{a.n} random points: max |log2|g| - reference| = {worst:.3g}, inside/outside disagreements: {flips}")


if __name__ == "__main__":
    sys.exit(main())
