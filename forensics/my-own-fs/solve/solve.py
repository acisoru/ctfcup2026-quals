#!/usr/bin/env python3
"""Carve deleted PNGs from a myfs image by following inode next-pointers."""

import struct
import sys

ISZ, HEAD, CONT = 1337, 51, 5

data = open(sys.argv[1] if len(sys.argv) > 1 else "disk.img", "rb").read()
n = len(data) // (ISZ + 1)
inode = lambda i: data[n + i * ISZ : n + (i + 1) * ISZ]

for i in range(n):
    b = inode(i)
    if b[4] != 1 or b[HEAD : HEAD + 8] != b"\x89PNG\r\n\x1a\n":
        continue
    size = struct.unpack_from("<Q", b, 15)[0]
    out, hdr = b"", HEAD
    while True:
        out += b[hdr:]
        nxt = struct.unpack_from("<I", b, 0)[0]
        if nxt == 0 or len(out) >= size:
            break
        b, hdr = inode(nxt), CONT
    name = f"carved_{i}.png"
    open(name, "wb").write(out[:size])
    print(f"inode {i} (used={data[i]}): {size} bytes -> {name}")
