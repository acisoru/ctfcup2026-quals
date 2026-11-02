#!/usr/bin/env python3
"""Decode the current Jai chirp telemetry format without Jai or its verifier.

Usage: python3 solve.py capture.wav [-o recovered.bin] [--report report.json]
Requires NumPy. Matplotlib is needed only by plot_writeup.py.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import sys
import zlib

import numpy as np

FS = 48_000
N = 2_048
FADE = 64
MAX_PAYLOAD = 4_096
ENDS = (4_000, 5_000, 7_000, 8_000)
PERMUTATION = np.array([2, 0, 3, 1], dtype=np.uint8)
INVERSE = np.argsort(PERMUTATION).astype(np.uint8)
PREAMBLE_KINDS = np.array([2, 0, 3, 1, 1, 3, 0, 2], dtype=np.uint8)
PREAMBLE_PHASES = np.array([0, 1, 0, 1, 1, 0, 1, 0], dtype=np.uint8)
PREAMBLE = 8
MASK32 = (1 << 32) - 1
MASK128 = (1 << 128) - 1
OUTPUT_MASKS = (0xA361C95B, 0x7D284E13)
WAV_HEADER = struct.Struct("<4sI4s4sIHHIIHH4sI")


class SolveError(ValueError):
    """Malformed capture, unsupported protocol, or unrecoverable corruption."""


@dataclass
class SolveResult:
    path: Path
    samples: np.ndarray
    kinds: np.ndarray
    physical_phases: np.ndarray
    correlations: np.ndarray
    scores: np.ndarray
    received: np.ndarray
    corrected: np.ndarray
    distances: np.ndarray
    source: np.ndarray
    masks: list[int]
    pivots: list[int | None]
    rank_history: np.ndarray
    initial_state: tuple[int, int, int, int]
    prng_bits: np.ndarray
    plaintext_bits: np.ndarray
    frame: bytes
    payload: bytes
    padding: int
    preamble_errors: int

    def report(self) -> dict:
        full_rank = np.flatnonzero(self.rank_history == 128)
        return {
            "capture": str(self.path),
            "sample_rate": FS,
            "samples_per_symbol": N,
            "physical_symbols": int(self.kinds.size),
            "coded_data_symbols": int(self.received.size),
            "rs_blocks": int(self.received.shape[0]),
            "logical_frame_bits": len(self.frame) * 8,
            "padding_labels": self.padding,
            "preamble_errors": self.preamble_errors,
            "corrected_symbols": int(self.distances.sum()),
            "correction_histogram": {
                str(d): int(np.count_nonzero(self.distances == d)) for d in range(3)
            },
            "equations": len(self.masks),
            "rank": int(self.rank_history[-1]),
            "first_full_rank_logical_symbol": int(full_rank[0] + 1),
            "initial_state_words_hex": [f"{w:08x}" for w in self.initial_state],
            "crc32_hex": f"{zlib.crc32(self.payload):08x}",
            "crc_verified": True,
            "payload_bytes": len(self.payload),
            "payload_hex": self.payload.hex(),
            "payload_utf8": self.payload.decode("utf-8", errors="replace"),
        }


def read_capture(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) < WAV_HEADER.size:
        raise SolveError("Truncated WAV header")
    header = WAV_HEADER.unpack_from(raw)
    expected = (
        b"RIFF",
        len(raw) - 8,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        FS,
        FS * 2,
        2,
        16,
        b"data",
        len(raw) - WAV_HEADER.size,
    )
    if header != expected:
        raise SolveError(
            "Expected canonical mono PCM16 / 48 kHz WAV with consistent lengths"
        )
    data_bytes = len(raw) - WAV_HEADER.size
    if data_bytes % (2 * N):
        raise SolveError("Capture ends inside a physical symbol")
    count = data_bytes // (2 * N)
    coded = count - PREAMBLE
    max_coded = ((MAX_PAYLOAD + 4) * 8 + 2) // 3 * 7
    if coded <= 0 or coded % 7 or coded > max_coded:
        raise SolveError("Invalid number of RS(7,3) data symbols")
    logical = coded // 7 * 3
    frame_bytes = logical // 8
    if not 12 <= frame_bytes <= MAX_PAYLOAD + 4 or logical - frame_bytes * 8 >= 3:
        raise SolveError("Invalid byte framing / source-label padding")
    # The view retains its bytes owner. Explicit LE works on any host byte order.
    return np.frombuffer(raw, dtype="<i2", offset=WAV_HEADER.size)


def make_templates() -> np.ndarray:
    n = np.arange(N, dtype=np.float64)
    t = n / FS
    envelope = np.ones(N, dtype=np.float64)
    envelope[:FADE] = n[:FADE] / FADE
    envelope[-FADE:] = (N - 1 - n[-FADE:]) / FADE
    slopes = (np.asarray(ENDS, dtype=np.float64) - 6_000) / (N / FS)
    phase = 2 * np.pi * (6_000 * t[None, :] + slopes[:, None] * t[None, :] ** 2 / 2)
    return envelope[None, :] * np.cos(phase)


def demodulate(
    samples: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    templates = make_templates()
    energy = np.sum(templates * templates, axis=1)
    blocks = samples.reshape(-1, N)
    correlations = np.empty((len(blocks), 4), dtype=np.float64)
    # Convert small batches, rather than allocating a float64 copy of the WAV.
    for start in range(0, len(blocks), 128):
        chunk = blocks[start : start + 128].astype(np.float64) / 32_767
        correlations[start : start + len(chunk)] = chunk @ templates.T
    scores = correlations**2 / energy[None, :]
    kinds = np.argmax(scores, axis=1).astype(np.uint8)
    selected = correlations[np.arange(len(blocks)), kinds]
    phases = (selected < 0).astype(np.uint8)
    return kinds, phases, correlations, scores


def gf8_mul(a: int, b: int) -> int:
    result = 0
    while b:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a & 8:
            a ^= 0b1011  # x^3 + x + 1, not integer arithmetic modulo eight
    return result


def rs_encode(data: tuple[int, int, int]) -> list[int]:
    a, b, c = data
    return [a ^ gf8_mul(b, x) ^ gf8_mul(c, gf8_mul(x, x)) for x in range(1, 8)]


def rs_codebook() -> tuple[np.ndarray, np.ndarray]:
    triples = np.array(
        [(v & 7, (v >> 3) & 7, (v >> 6) & 7) for v in range(512)],
        dtype=np.uint8,
    )
    codewords = np.array(
        [rs_encode(tuple(map(int, t))) for t in triples], dtype=np.uint8
    )
    return triples, codewords


def correct_rs(received: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    triples, codewords = rs_codebook()
    source = np.empty((len(received), 3), dtype=np.uint8)
    corrected = np.empty_like(received)
    distances = np.empty(len(received), dtype=np.uint8)
    for block, symbols in enumerate(received):
        distance = np.count_nonzero(codewords != symbols[None, :], axis=1)
        candidates = np.flatnonzero(distance <= 2)
        if len(candidates) != 1:
            raise SolveError(
                f"RS block {block} has no unique codeword within two symbol errors"
            )
        candidate = int(candidates[0])
        source[block] = triples[candidate]
        corrected[block] = codewords[candidate]
        distances[block] = distance[candidate]
    return source.ravel(), corrected, distances


def next_bit(state: list[int]) -> int:
    a, b, c, d = state
    t = (b << 9) & MASK32
    c ^= a
    d ^= b
    b ^= c
    a ^= d
    c ^= t
    d = ((d << 11) | (d >> 21)) & MASK32
    state[:] = a, b, c, d
    return ((d & OUTPUT_MASKS[0]).bit_count() ^ (b & OUTPUT_MASKS[1]).bit_count()) & 1


class SymbolicGenerator:
    """Every state bit is a 128-bit coefficient mask over the initial state."""

    def __init__(self) -> None:
        self.words = [[1 << (32 * w + b) for b in range(32)] for w in range(4)]

    def next_mask(self) -> int:
        a, b, c, d = self.words
        t = [0] * 9 + b[:23]  # 32-bit left shift by nine
        c = [x ^ y for x, y in zip(c, a)]
        d = [x ^ y for x, y in zip(d, b)]
        b = [x ^ y for x, y in zip(b, c)]
        a = [x ^ y for x, y in zip(a, d)]
        c = [x ^ y for x, y in zip(c, t)]
        d = d[-11:] + d[:-11]  # rotate bits, with index zero representing the LSB
        self.words = [a, b, c, d]
        mask = 0
        for bit in range(32):
            if OUTPUT_MASKS[0] >> bit & 1:
                mask ^= d[bit]
            if OUTPUT_MASKS[1] >> bit & 1:
                mask ^= b[bit]
        return mask


def recover_state(
    source: np.ndarray,
) -> tuple[tuple[int, int, int, int], list[int], list[int | None], np.ndarray]:
    symbolic = SymbolicGenerator()
    pivots: list[int | None] = [None] * 128
    masks: list[int] = []
    rank_history = np.empty(len(source), dtype=np.uint16)
    rank = 0
    for index, label in enumerate(source):
        for shift in (2, 1):
            mask = symbolic.next_mask()
            masks.append(mask)
            rhs = int(label) >> shift & 1
            row = mask | (rhs << 128)
            while row & MASK128:
                pivot = ((row & MASK128) & -(row & MASK128)).bit_length() - 1
                if pivots[pivot] is None:
                    pivots[pivot] = row
                    rank += 1
                    break
                row ^= pivots[pivot]
            else:
                if row >> 128 & 1:
                    raise SolveError(
                        f"Inconsistent GF(2) observations at logical symbol {index}"
                    )
        symbolic.next_mask()  # Hidden h_i: advance, but add no equation.
        rank_history[index] = rank
    if rank != 128:
        raise SolveError(f"State is not uniquely recoverable: rank {rank}/128")
    solution = 0
    for pivot in range(127, -1, -1):
        row = pivots[pivot]
        assert row is not None
        value = ((row >> 128) & 1) ^ ((row & MASK128 & solution).bit_count() & 1)
        solution |= value << pivot
    initial = tuple((solution >> (32 * w)) & MASK32 for w in range(4))
    if not any(initial):
        raise SolveError("Recovered forbidden all-zero generator state")
    return initial, masks, pivots, rank_history


def solve(path: Path) -> SolveResult:
    samples = read_capture(path)
    kinds, phases, correlations, scores = demodulate(samples)
    preamble_errors = int(
        np.count_nonzero(
            (kinds[:PREAMBLE] != PREAMBLE_KINDS)
            | (phases[:PREAMBLE] != PREAMBLE_PHASES),
        )
    )
    labels = (INVERSE[kinds[PREAMBLE:]] << 1) | phases[PREAMBLE:]
    received = labels.reshape(-1, 7)
    source, corrected, distances = correct_rs(received)
    frame_bytes = len(source) // 8
    frame_bits = frame_bytes * 8
    padding = len(source) - frame_bits
    if np.any(source[frame_bits:] != 0):
        raise SolveError("Nonzero padding labels after RS correction")
    logical = source[:frame_bits]
    initial, masks, pivots, rank_history = recover_state(logical)
    state = list(initial)
    stream = np.empty((frame_bits, 3), dtype=np.uint8)
    for i in range(frame_bits):
        stream[i] = [next_bit(state) for _ in range(3)]
    if not np.array_equal((stream[:, 0] << 1) | stream[:, 1], logical >> 1):
        raise SolveError(
            "Recovered state does not reproduce every observed selector bit"
        )
    q = logical & 1
    previous_q = np.concatenate((np.zeros(1, dtype=np.uint8), q[:-1]))
    plaintext = q ^ previous_q ^ stream[:, 2]
    frame = np.packbits(plaintext, bitorder="big").tobytes()
    payload, checksum = frame[:-4], frame[-4:]
    if int.from_bytes(checksum, "little") != zlib.crc32(payload):
        raise SolveError("CRC-32 mismatch: residual phase/data corruption remains")
    return SolveResult(
        path,
        samples,
        kinds,
        phases,
        correlations,
        scores,
        received,
        corrected,
        distances,
        source,
        masks,
        pivots,
        rank_history,
        initial,
        stream,
        plaintext,
        frame,
        payload,
        padding,
        preamble_errors,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument(
        "-o", "--output", type=Path, help="Write exact recovered payload bytes"
    )
    parser.add_argument(
        "--report", type=Path, help="Write diagnostics and recovered state as JSON"
    )
    args = parser.parse_args()
    paths = [
        p.resolve() for p in (args.capture, args.output, args.report) if p is not None
    ]
    if len(set(paths)) != len(paths):
        parser.error("Input, payload output, and report must use different paths")
    try:
        result = solve(args.capture)
        if args.output is not None:
            args.output.write_bytes(result.payload)
        if args.report is not None:
            args.report.write_text(json.dumps(result.report(), indent=2) + "\n")
    except (OSError, SolveError) as error:
        print(f"solve: {error}", file=sys.stderr)
        return 1
    print(
        f"{len(result.payload)} payload bytes; rank 128/128; "
        f"{int(result.distances.sum())} corrected physical symbols; CRC-32 verified",
        file=sys.stderr,
    )
    if result.preamble_errors:
        print(
            f"Diagnostic preamble mismatches: {result.preamble_errors}/8",
            file=sys.stderr,
        )
    try:
        print(result.payload.decode("utf-8"))
    except UnicodeDecodeError:
        print(repr(result.payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
