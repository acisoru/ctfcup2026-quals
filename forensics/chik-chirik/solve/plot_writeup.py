#!/usr/bin/env python3
"""Produce the writeup's PNG/SVG figures from a real solved capture.

python3 plot_writeup.py examples/demo.wav --output figures \
    --corrupted-demo examples/demo-corrupted.wav

The optional corruption example replaces two whole waveforms per RS block.
It demonstrates symbol substitution correction, not a random-noise measurement.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "chirp-matplotlib")
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.ticker import FuncFormatter
import numpy as np

from solve import (
    ENDS,
    FADE,
    FS,
    N,
    PERMUTATION,
    PREAMBLE,
    SolveResult,
    make_templates,
    solve,
)

COLORS = ["#2459a8", "#e18b22", "#139585", "#8756b2"]
RED = "#c34545"
GREEN = "#168266"
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.fonttype": "none",
        "savefig.dpi": 180,
    }
)


def save(fig, directory: Path, stem: str) -> None:
    for extension in ("png", "svg"):
        fig.savefig(
            directory / f"{stem}.{extension}", bbox_inches="tight", facecolor="white"
        )
    plt.close(fig)


def pipeline(result: SolveResult, directory: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 5.1))
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    top = [
        "Payload\n+ CRC-32",
        "Logical symbols\nu | v | q",
        "RS(7,3)\n3 labels → 7",
        "Chirp + sign\n8 physical labels",
        "PCM16 WAV\n48 kHz",
    ]
    bottom = [
        "Recover bytes\nverify CRC-32",
        "GF(2) state solve\nundo phase mask",
        "RS correction\n≤2 errors / block",
        "4 matched filters\nrecover label",
        "Read samples\n2,048 per symbol",
    ]
    xs = np.linspace(0.018, 0.812, 5)
    width, height = 0.17, 0.23
    for row, y, color in ((top, 0.62, COLORS[0]), (bottom, 0.17, GREEN)):
        for x, label in zip(xs, row):
            box = FancyBboxPatch(
                (x, y),
                width,
                height,
                boxstyle="round,pad=0.01",
                ec=color,
                fc=color + "12",
                lw=1.8,
            )
            ax.add_patch(box)
            ax.text(
                x + width / 2,
                y + height / 2,
                label,
                ha="center",
                va="center",
                fontsize=11,
            )
    for i in range(4):
        ax.add_patch(
            FancyArrowPatch(
                (xs[i] + width + 0.003, 0.735),
                (xs[i + 1] - 0.008, 0.735),
                arrowstyle="-|>",
                mutation_scale=15,
                color=COLORS[0],
            )
        )
        ax.add_patch(
            FancyArrowPatch(
                (xs[i + 1] - 0.008, 0.285),
                (xs[i] + width + 0.003, 0.285),
                arrowstyle="-|>",
                mutation_scale=15,
                color=GREEN,
            )
        )
    ax.add_patch(
        FancyArrowPatch(
            (xs[-1] + width / 2, 0.60),
            (xs[-1] + width / 2, 0.42),
            arrowstyle="-|>",
            mutation_scale=15,
            color="#555555",
        )
    )
    ax.text(0.02, 0.93, "Transmitter", weight="bold", color=COLORS[0], fontsize=14)
    ax.text(
        0.02,
        0.47,
        "Solver: reverse the signal path",
        weight="bold",
        color=GREEN,
        fontsize=14,
    )
    ax.text(
        0.5,
        0.035,
        f"Actual example: {len(result.payload)} payload bytes · {len(result.received)} RS blocks · {len(result.kinds)} physical symbols · rank 128",
        ha="center",
        fontsize=11,
    )
    save(fig, directory, "01_pipeline")


def chirps(directory: Path) -> None:
    templates = make_templates()
    t_ms = np.arange(N) / FS * 1000
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    for kind, end in enumerate(ENDS):
        axes[0].plot(
            t_ms,
            (6000 + (end - 6000) * np.arange(N) / N) / 1000,
            color=COLORS[kind],
            lw=2.2,
            label=f"kind {kind}: 6 → {end / 1000:g} kHz",
        )
        axes[1].plot(
            t_ms[:96], 0.35 * templates[kind, :96] + kind, color=COLORS[kind], lw=1.2
        )
    axes[0].set(
        title="Four known linear chirps",
        xlabel="Time inside one symbol (ms)",
        ylabel="Instantaneous frequency (kHz)",
        xlim=(0, N / FS * 1000),
        ylim=(3.7, 8.3),
    )
    axes[0].legend(loc="upper left", ncol=2)
    axes[0].grid(alpha=0.2)
    axes[1].set(
        title="First 2 ms of the real-valued templates, vertically offset",
        xlabel="Time inside one symbol (ms)",
        ylabel="Kind (vertical offset)",
        yticks=range(4),
        xlim=(0, 2),
    )
    axes[1].text(
        0.98,
        0.025,
        f"Peak signal: 0.35 · first {FADE} samples fade in\nPolarity 1 multiplies the entire waveform by −1",
        transform=axes[1].transAxes,
        ha="right",
        va="bottom",
        bbox=dict(fc="white", ec="#dddddd", alpha=0.94),
        fontsize=10,
    )
    save(fig, directory, "02_chirp_templates")


def capture_view(result: SolveResult, directory: Path) -> None:
    symbols = min(len(result.kinds), 15)
    signal = result.samples[: symbols * N].astype(np.float64) / 32767
    time = np.arange(len(signal)) / FS
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), layout="constrained", sharex=True)
    axes[0].plot(time, signal, color=COLORS[0], lw=0.45, rasterized=True)
    axes[0].set(
        title="Actual Jai capture: calibration followed by encoded data",
        ylabel="Normalized PCM amplitude",
        ylim=(-0.45, 0.45),
    )
    for i in range(symbols):
        kind = int(result.kinds[i])
        axes[0].axvspan(i * N / FS, (i + 1) * N / FS, color=COLORS[kind], alpha=0.06)
        axes[0].text(
            (i + 0.5) * N / FS, 0.405, str(kind), ha="center", va="center", fontsize=9
        )
    _, _, _, image = axes[1].specgram(
        signal, NFFT=256, Fs=FS, noverlap=224, cmap="magma", vmin=-95, vmax=-35
    )
    axes[1].set(
        title="Spectrogram: each slope is visible; polarity is absent from power",
        xlabel="Capture time (s)",
        ylabel="Frequency (kHz)",
        ylim=(3000, 9000),
    )
    axes[1].yaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{value / 1000:g}")
    )
    fig.colorbar(image, ax=axes[1], label="Power spectral density (dB/Hz)", pad=0.015)
    for ax in axes:
        for i in range(1, symbols):
            ax.axvline(
                i * N / FS,
                color="white" if ax is axes[1] else "#aaaaaa",
                alpha=0.35,
                lw=0.6,
            )
        ax.axvline(PREAMBLE * N / FS, color=RED, lw=2, ls="--")
        ax.set_xlim(0, symbols * N / FS)
    axes[0].text(
        PREAMBLE * N / FS + 0.008, -0.4, "coded data starts", color=RED, fontsize=10
    )
    save(fig, directory, "03_capture_spectrogram")


def matched_filters(result: SolveResult, directory: Path) -> None:
    templates = make_templates()
    energy = np.sum(templates**2, axis=1)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for column, symbol in enumerate((0, 1)):
        kind = int(result.kinds[symbol])
        phase = int(result.physical_phases[symbol])
        signal = (
            result.samples[symbol * N : (symbol + 1) * N].astype(np.float64) / 32767
        )
        sign = 1 if phase == 0 else -1
        t = np.arange(128) / FS * 1000
        axes[0, column].plot(
            t, signal[:128], color="#999999", lw=1.4, label="captured samples"
        )
        axes[0, column].plot(
            t,
            sign * 0.35 * templates[kind, :128],
            color=COLORS[kind],
            lw=1,
            label="selected signed template",
        )
        axes[0, column].set(
            title=f"Preamble symbol {symbol}: kind {kind}, polarity {phase}",
            xlabel="Time inside symbol (ms)",
            ylabel="Amplitude",
        )
        axes[0, column].legend(fontsize=9, loc="upper left")
        amplitudes = result.correlations[symbol] / energy
        axes[1, column].bar(
            range(4),
            amplitudes,
            color=[GREEN if k == kind else "#b8c0cc" for k in range(4)],
        )
        axes[1, column].axhline(0, color="#555555", lw=1)
        axes[1, column].set(
            xlabel="Candidate chirp kind",
            ylabel=r"Signed amplitude estimate $c_k/E_k$",
            xticks=range(4),
            ylim=(-0.43, 0.43),
        )
        axes[1, column].set_title(
            "Positive correlation → phase 0"
            if phase == 0
            else "Negative correlation → phase 1"
        )
        axes[1, column].text(
            kind,
            amplitudes[kind] + (0.028 if phase == 0 else -0.055),
            f"{amplitudes[kind]:+.3f}",
            ha="center",
            color=GREEN,
            weight="bold",
        )
    save(fig, directory, "04_matched_filter_phase")


def make_corrupted_copy(result: SolveResult, output: Path) -> SolveResult:
    if output.resolve() == result.path.resolve():
        raise ValueError("Corruption demo must not overwrite the original capture")
    raw = bytearray(result.path.read_bytes())
    templates = make_templates()
    for block in range(len(result.received)):
        for position in (0, 4):
            label = int(result.corrected[block, position]) ^ 7
            kind = int(PERMUTATION[label >> 1])
            sign = 1 if label & 1 == 0 else -1
            pcm = np.trunc(sign * 0.35 * templates[kind] * 32767).astype("<i2")
            offset = 44 + (PREAMBLE + block * 7 + position) * N * 2
            raw[offset : offset + N * 2] = pcm.tobytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    damaged = solve(output)
    if (
        damaged.payload != result.payload
        or damaged.initial_state != result.initial_state
    ):
        raise ValueError(
            "Corruption demonstration did not recover the original data/state"
        )
    output.with_suffix(".json").write_text(
        json.dumps(damaged.report(), indent=2) + "\n"
    )
    return damaged


def rs_correction(result: SolveResult, directory: Path) -> None:
    block = int(np.argmax(result.distances))
    received, corrected = result.received[block], result.corrected[block]
    source = result.source[block * 3 : (block + 1) * 3]
    fig, axes = plt.subplots(
        3,
        1,
        figsize=(12, 6.5),
        layout="constrained",
        gridspec_kw={"height_ratios": [1, 1, 1]},
    )
    rows = [
        (received, "Demodulated physical labels"),
        (corrected, "Nearest valid RS codeword"),
        (source, "Recovered polynomial coefficients / logical labels"),
    ]
    for axis, (labels, title) in zip(axes, rows):
        axis.imshow(
            labels[None, :],
            cmap="viridis",
            vmin=0,
            vmax=7,
            aspect="auto",
            extent=(-0.5, len(labels) - 0.5, -0.5, 0.5),
        )
        for j, label in enumerate(labels):
            axis.text(
                j,
                0,
                f"{int(label)}\n{int(label):03b}",
                ha="center",
                va="center",
                color="#102330" if int(label) >= 5 else "white",
                weight="bold",
                fontsize=13,
            )
            if axis is axes[0] and received[j] != corrected[j]:
                axis.add_patch(
                    plt.Rectangle(
                        (j - 0.49, -0.49), 0.98, 0.98, fill=False, ec=RED, lw=3.5
                    )
                )
        axis.set(title=title, xticks=range(len(labels)), yticks=[])
    axes[0].set_xlabel(
        "Physical position inside the seven-symbol block (red = wrong decision)"
    )
    axes[1].set_xlabel(
        f"Block {block}: Hamming distance {int(result.distances[block])}, correction radius 2"
    )
    axes[2].set_xlabel("Coefficient a₀, a₁, a₂; each label contains u | v | q")
    fig.suptitle("Reed–Solomon correction of wrong physical labels", fontsize=15)
    save(fig, directory, "05_rs_symbol_correction")


def masks_as_matrix(masks: list[int]) -> np.ndarray:
    return np.array(
        [[(mask >> bit) & 1 for bit in range(128)] for mask in masks], dtype=np.uint8
    )


def linear_algebra(result: SolveResult, directory: Path) -> None:
    count = min(256, len(result.masks))
    original = masks_as_matrix(result.masks[:count])
    reduced = masks_as_matrix(
        [int(row) & ((1 << 128) - 1) for row in result.pivots if row is not None]
    )
    fig = plt.figure(figsize=(13, 9), layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=(2, 1))
    ax1, ax2 = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
    ax3 = fig.add_subplot(grid[1, :])
    ax1.imshow(
        original, cmap="Greys", vmin=0, vmax=1, aspect="auto", interpolation="nearest"
    )
    ax1.set(
        title=f"First {count} observed-bit coefficient rows",
        xlabel="Initial state bit (0…127)",
        ylabel="Observed equation",
    )
    ax2.imshow(
        reduced, cmap="Greys", vmin=0, vmax=1, aspect="auto", interpolation="nearest"
    )
    ax2.set(
        title="128 independent pivot rows after elimination",
        xlabel="Initial state bit (0…127)",
        ylabel="Lowest set bit / pivot",
    )
    x = np.arange(1, len(result.rank_history) + 1)
    ax3.plot(x, result.rank_history, color=COLORS[0], lw=2.2)
    first = int(np.flatnonzero(result.rank_history == 128)[0] + 1)
    ax3.axhline(128, color=GREEN, ls="--", lw=1)
    ax3.axvline(first, color=GREEN, ls="--", lw=1)
    ax3.annotate(
        f"Full rank after {first} logical symbols",
        (first, 128),
        xytext=(first + 10, 88),
        arrowprops=dict(arrowstyle="->", color=GREEN),
        color=GREEN,
    )
    ax3.set(
        title="Two observed PRNG bits per logical symbol determine 128 hidden state bits",
        xlabel="Logical frame symbols processed",
        ylabel="GF(2) rank",
        ylim=(0, 137),
        xlim=(1, len(x)),
    )
    ax3.grid(alpha=0.2)
    save(fig, directory, "06_gf2_state_recovery")


def unmasking(result: SolveResult, directory: Path) -> None:
    count = min(64, len(result.plaintext_bits))
    q = result.source[:count] & 1
    previous = np.concatenate((np.zeros(1, dtype=np.uint8), q[:-1]))
    hidden = result.prng_bits[:count, 2]
    plain = result.plaintext_bits[:count]
    matrix = np.vstack((q, previous, hidden, plain))
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(14, 5.5),
        layout="constrained",
        gridspec_kw={"height_ratios": (2, 1)},
    )
    axes[0].imshow(
        matrix, cmap="Blues", vmin=0, vmax=1, aspect="auto", interpolation="nearest"
    )
    axes[0].set(
        title=r"Undo the logical differential phase: $p_i = q_i \oplus q_{i-1} \oplus h_i$",
        xlabel="Logical frame bit index",
        yticks=range(4),
        yticklabels=["corrected qᵢ", "previous qᵢ₋₁", "regenerated hᵢ", "plaintext pᵢ"],
    )
    for bit in range(count):
        for row in range(4):
            axes[0].text(
                bit,
                row,
                str(int(matrix[row, bit])),
                ha="center",
                va="center",
                fontsize=7.5,
                color="white" if matrix[row, bit] else "#17375e",
            )
    for boundary in range(7, count - 1, 8):
        axes[0].axvline(boundary + 0.5, color="#e18b22", lw=1.5)
    axes[1].axis("off")
    byte_count = count // 8
    cells = [
        [str(i) for i in range(byte_count)],
        [f"{result.frame[i]:08b}" for i in range(byte_count)],
        [f"0x{result.frame[i]:02x}" for i in range(byte_count)],
        [
            chr(result.frame[i]) if 32 <= result.frame[i] < 127 else "·"
            for i in range(byte_count)
        ],
    ]
    table = axes[1].table(
        cellText=cells,
        rowLabels=["Byte index", "MSB-first bits", "Hex", "ASCII"],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.45)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if row == 3:
            cell.set_facecolor("#e6f2ee")
    save(fig, directory, "07_phase_unmasking_bytes")


def noise_comparison(
    baseline: SolveResult, noisy: SolveResult, directory: Path
) -> None:
    wrong = np.flatnonzero(noisy.received.ravel() != noisy.corrected.ravel())
    if not len(wrong):
        raise ValueError(
            "Noise illustration needs a capture with at least one corrected decision"
        )
    symbol = PREAMBLE + int(wrong[0])
    templates = make_templates()
    energy = np.sum(templates**2, axis=1)
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    for column, (result, title, color) in enumerate(
        (
            (baseline, "Original Jai recording", GREEN),
            (noisy, "Added random noise and sample clipping", RED),
        )
    ):
        y = result.samples[symbol * N : (symbol + 1) * N].astype(np.float64) / 32767
        t = np.arange(192) / FS * 1000
        axes[0, column].plot(t, y[:192], color=color, lw=0.8)
        axes[0, column].set(
            title=title,
            xlabel="Time inside physical symbol (ms)",
            ylabel="Normalized PCM amplitude",
            ylim=(-1.08, 1.08),
        )
        kind, phase = int(result.kinds[symbol]), int(result.physical_phases[symbol])
        amplitudes = result.correlations[symbol] / energy
        axes[1, column].bar(
            range(4),
            amplitudes,
            color=[color if k == kind else "#b8c0cc" for k in range(4)],
        )
        axes[1, column].axhline(0, color="#555555", lw=1)
        axes[1, column].set(
            title=f"Hard decision: kind {kind}, polarity {phase}",
            xlabel="Candidate chirp kind",
            ylabel=r"Signed amplitude estimate $c_k/E_k$",
            xticks=range(4),
            ylim=(-0.43, 0.43),
        )
    clipped = np.mean(np.abs(noisy.samples.astype(np.int32)) == 32767)
    label = int(noisy.corrected.ravel()[symbol - PREAMBLE])
    fig.suptitle(
        f"Physical symbol {symbol}: raw decision changes; RS restores label {label:03b}\n{int(noisy.distances.sum())} corrected labels in this capture · {clipped:.1%} of samples clipped",
        fontsize=14,
    )
    save(fig, directory, "08_additive_noise_correction")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, default=Path("figures"))
    parser.add_argument(
        "--corrupted-demo",
        type=Path,
        help="Create a separate capture with two waveform substitutions per block",
    )
    parser.add_argument(
        "--damaged-capture",
        type=Path,
        help="Use an already-corrupted capture for the RS illustration",
    )
    parser.add_argument(
        "--noisy-capture",
        type=Path,
        help="Add an eighth figure comparing an additive-noise variant",
    )
    args = parser.parse_args()
    if args.corrupted_demo is not None and args.damaged_capture is not None:
        parser.error("Choose --corrupted-demo or --damaged-capture")
    result = solve(args.capture)
    if args.corrupted_demo is not None:
        damaged = make_corrupted_copy(result, args.corrupted_demo)
    elif args.damaged_capture is not None:
        damaged = solve(args.damaged_capture)
    else:
        damaged = result
    if (
        damaged.payload != result.payload
        or damaged.initial_state != result.initial_state
    ):
        raise ValueError(
            "RS illustration must come from the same logical frame as the baseline"
        )
    noisy = solve(args.noisy_capture) if args.noisy_capture is not None else None
    if noisy is not None and (
        noisy.payload != result.payload or noisy.initial_state != result.initial_state
    ):
        raise ValueError(
            "Noise illustration must come from the same logical frame as the baseline"
        )
    args.output.mkdir(parents=True, exist_ok=True)
    pipeline(result, args.output)
    chirps(args.output)
    capture_view(result, args.output)
    matched_filters(result, args.output)
    rs_correction(damaged, args.output)
    linear_algebra(result, args.output)
    unmasking(result, args.output)
    if noisy is not None:
        noise_comparison(result, noisy, args.output)
    metadata = {
        "baseline": result.report(),
        "rs_illustration": damaged.report(),
        "rs_illustration_method": "two waveform substitutions per block"
        if args.corrupted_demo
        else "provided capture",
        "numpy_version": np.__version__,
        "matplotlib_version": matplotlib.__version__,
        "figure_formats": ["png", "svg"],
    }
    if noisy is not None:
        metadata["noise_illustration"] = noisy.report()
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(
        f"Wrote {8 if noisy is not None else 7} PNG/SVG figure pairs to {args.output}"
    )


if __name__ == "__main__":
    main()
