#!/usr/bin/env python3
"""Solver for MMM.

The binary checks that the flag bytes form an eigenvector of a 40x40 integer
matrix stored in .rodata, then compares SHA-256 of the input with a digest.
We pull the matrix out of the ELF by its symbol, take the eigenvector for the
only real integer eigenvalue, and scale it so the first byte is 'c'.

usage: solve.py [path/to/mmm]   (defaults to the binary inside public/mmm.zip)
"""
import hashlib
import io
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np
from elftools.elf.elffile import ELFFile

N = 40


def read_symbol(elf: ELFFile, name: str, size: int) -> bytes:
    symtab = elf.get_section_by_name(".symtab")
    (sym,) = symtab.get_symbol_by_name(name)
    sec = elf.get_section(sym["st_shndx"])
    off = sym["st_value"] - sec["sh_addr"] + sec["sh_offset"]
    elf.stream.seek(off)
    return elf.stream.read(size)


def main() -> None:
    if len(sys.argv) > 1:
        data = Path(sys.argv[1]).read_bytes()
    else:
        archive = Path(__file__).parent.parent / "public" / "mmm.zip"
        data = zipfile.ZipFile(archive).read("mmm")
    elf = ELFFile(io.BytesIO(data))
    raw_matrix = read_symbol(elf, "_ZL6MATRIX", N * N * 8)
    digest = read_symbol(elf, "_ZL9FLAG_HASH", 32)

    M = np.array(struct.unpack(f"<{N * N}q", raw_matrix), dtype=float).reshape(N, N)
    vals, vecs = np.linalg.eig(M)

    for idx in range(N):
        if abs(vals[idx].imag) > 1e-6:
            continue
        vec = vecs[:, idx].real
        vec = vec / vec[0] * ord("c")
        cand = np.rint(vec).astype(int)
        if not np.allclose(vec, cand, atol=1e-6) or not all(32 <= c < 127 for c in cand):
            continue
        flag = bytes(int(c) for c in cand)
        if hashlib.sha256(flag).digest() == digest:
            print(f"eigenvalue = {vals[idx].real:.0f}")
            print(flag.decode())
            return
    raise SystemExit("no suitable eigenvector found")


if __name__ == "__main__":
    main()
