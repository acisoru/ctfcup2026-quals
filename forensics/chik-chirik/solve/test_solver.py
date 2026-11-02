#!/usr/bin/env python3
"""Independent solver checks. No original challenge file is edited."""

from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from solve import (
    FS,
    N,
    PERMUTATION,
    PREAMBLE,
    SolveError,
    SymbolicGenerator,
    correct_rs,
    gf8_mul,
    make_templates,
    next_bit,
    recover_state,
    rs_codebook,
    rs_encode,
    solve,
)

HERE = Path(__file__).resolve().parent
DEMO = HERE / "examples/demo.wav"
DAMAGED = HERE / "examples/demo-corrupted.wav"
DEMO_PAYLOAD = b"CTFCUP{chirps_leak_linear_state}"


def replace_block(raw: bytearray, block: int, labels: list[int]) -> None:
    templates = make_templates()
    for j, label in enumerate(labels):
        sign = -1 if label & 1 else 1
        waveform = sign * 0.35 * templates[int(PERMUTATION[label >> 1])]
        offset = 44 + (PREAMBLE + block * 7 + j) * N * 2
        raw[offset : offset + N * 2] = (
            np.trunc(waveform * 32767).astype("<i2").tobytes()
        )


class SolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clean = solve(DEMO)

    def test_known_generator_vector(self):
        state = [0x01234567, 0x89ABCDEF, 0xFEDCBA98, 0x76543210]
        stream = 0
        for _ in range(64):
            stream = stream << 1 | next_bit(state)
        self.assertEqual(stream, 0x2ECA80D248E9E1AF)

    def test_symbolic_generator_against_all_basis_states(self):
        symbolic = SymbolicGenerator()
        masks = [symbolic.next_mask() for _ in range(192)]
        for basis in range(128):
            state = [0, 0, 0, 0]
            state[basis // 32] = 1 << (basis % 32)
            for mask in masks:
                self.assertEqual(next_bit(state), (mask >> basis) & 1)

    def test_field_and_rs_vector(self):
        self.assertEqual(gf8_mul(2, 4), 3)
        self.assertEqual(rs_encode((1, 2, 3)), [0, 2, 3, 3, 2, 0, 1])

    def test_full_codebook_minimum_distance(self):
        _, codes = rs_codebook()
        distances = np.count_nonzero(codes[:, None, :] != codes[None, :, :], axis=2)
        np.fill_diagonal(distances, 8)
        self.assertEqual(int(distances.min()), 5)

    def test_all_two_symbol_errors_for_representative_codewords(self):
        triples, codes = rs_codebook()
        received, expected = [], []
        for candidate in (0, 73, 197, 511):
            for first in range(6):
                for second in range(first + 1, 7):
                    for delta1 in range(1, 8):
                        for delta2 in range(1, 8):
                            row = codes[candidate].copy()
                            row[first] ^= delta1
                            row[second] ^= delta2
                            received.append(row)
                            expected.append(triples[candidate])
        source, _, distances = correct_rs(np.array(received, dtype=np.uint8))
        np.testing.assert_array_equal(source.reshape(-1, 3), expected)
        np.testing.assert_array_equal(distances, np.full(len(received), 2))

    def test_out_of_radius_rs_block(self):
        with self.assertRaisesRegex(SolveError, "RS block 0"):
            correct_rs(np.array([[1, 1, 1, 0, 0, 0, 0]], dtype=np.uint8))

    def test_clean_capture_and_rank(self):
        self.assertEqual(self.clean.payload, DEMO_PAYLOAD)
        self.assertEqual(int(self.clean.distances.sum()), 0)
        self.assertEqual(int(self.clean.rank_history[63]), 128)
        self.assertLess(int(self.clean.rank_history[62]), 128)

    def test_damaged_waveforms(self):
        damaged = solve(DAMAGED)
        self.assertEqual(damaged.payload, DEMO_PAYLOAD)
        self.assertEqual(damaged.initial_state, self.clean.initial_state)
        self.assertEqual(int(damaged.distances.sum()), 2 * len(damaged.received))
        np.testing.assert_array_equal(damaged.corrected, self.clean.corrected)

    def test_additive_noise_fixture(self):
        noisy = solve(HERE / "examples/demo-noisy.wav")
        self.assertEqual(noisy.payload, DEMO_PAYLOAD)
        self.assertEqual(noisy.initial_state, self.clean.initial_state)
        self.assertGreater(int(noisy.distances.sum()), 0)
        np.testing.assert_array_equal(noisy.corrected, self.clean.corrected)

    def test_rank_and_inconsistency_rejection(self):
        with self.assertRaisesRegex(SolveError, "rank"):
            recover_state(self.clean.source[:10])
        changed = self.clean.source[: len(self.clean.frame) * 8].copy()
        changed[100] ^= 4
        with self.assertRaisesRegex(SolveError, "Inconsistent GF"):
            recover_state(changed)

    def test_crc_rejects_valid_rs_with_changed_phase(self):
        raw = bytearray(DEMO.read_bytes())
        first = list(map(int, self.clean.source[:3]))
        first[0] ^= 1  # Keep u/v; change q. RS encoding is still valid.
        replace_block(raw, 0, rs_encode(tuple(first)))
        with tempfile.TemporaryDirectory(prefix="chirp-python-test-") as directory:
            path = Path(directory) / "bad-crc.wav"
            path.write_bytes(raw)
            with self.assertRaisesRegex(SolveError, "CRC-32"):
                solve(path)

    def test_bad_headers_and_truncation(self):
        original = DEMO.read_bytes()
        wrong_rate = bytearray(original)
        struct.pack_into("<I", wrong_rate, 24, FS + 1)
        with tempfile.TemporaryDirectory(prefix="chirp-python-test-") as directory:
            path = Path(directory) / "bad.wav"
            for content in (b"", original[:20], original[:-1], bytes(wrong_rate)):
                path.write_bytes(content)
                with self.assertRaises(SolveError):
                    solve(path)

    def test_bad_padding_framing(self):
        # Add one whole RS block: byte count is unchanged but padding becomes 3.
        raw = bytearray(DEMO.read_bytes()) + bytearray(7 * N * 2)
        struct.pack_into("<I", raw, 4, len(raw) - 8)
        struct.pack_into("<I", raw, 40, len(raw) - 44)
        with tempfile.TemporaryDirectory(prefix="chirp-python-test-") as directory:
            path = Path(directory) / "bad-padding.wav"
            path.write_bytes(raw)
            with self.assertRaisesRegex(SolveError, "padding"):
                solve(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
