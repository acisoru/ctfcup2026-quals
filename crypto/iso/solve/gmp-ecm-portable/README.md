# Portable GPU-ECM (CGBN) pipeline

Reproducible GPU build of [sethtroisi/gmp-ecm](https://github.com/sethtroisi/gmp-ecm)
with a custom CGBN kernel, plus a Python driver that splits ECM into:

1. **Stage 1 on one or more GPUs** (GMP-ECM `-gpu`, batched curves);
2. **Stage 2 on many CPU threads** (save file split into per-thread chunks).

## Pinned versions

| component | commit |
|---|---|
| gmp-ecm | `8ea5e214fdf2f0ddf9415141b8dc039ed6f5874e` |
| CGBN | `114601b07ae8c3e4d46b250208ea8d9def7a12f0` |

The patch `patches/0001-custom-cgbn-kernel.patch`:

- adds a compile-time custom kernel `ECM_CUSTOM_BITS` / `ECM_CUSTOM_TPI`;
- drops unused large stock kernels to reduce build time;
- selects the custom kernel for the target N size.

Build picks `kernel_bits = round_up(N_bits + 6, 128)` and
`TPI = 16` for kernels up to 4096 bits, `TPI = 32` above that.

## Requirements

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y git build-essential automake autoconf libtool m4 libgmp-dev nvidia-cuda-toolkit
```

Also required: NVIDIA driver + CUDA toolkit (`nvcc`, `cuda.h`, `libcudart`).
Build on the machine where you will run it: the CUDA runtime path is baked in
at link time.

## Build

```bash
cd /home/ubuntu/gmp-ecm-portable
./build.sh --bits 2300
```

For 2300 bits this builds a **2432-bit kernel with TPI=16** and installs
`bin/ecm`. Build info is written to `build-info.txt`.

Common options:

```bash
./build.sh --bits 5000 --sm 89          # custom 5120-bit kernel, TPI=32
./build.sh --bits 2300 --jobs 32
./build.sh --bits 2300 --generic        # no -march=native
./build.sh --bits 2300 --clean          # wipe build/src and clone again
```

`--sm` is auto-detected with `nvidia-smi` (e.g. RTX 4090 -> 89, H100 -> 90).
For a build host without a GPU, pass it explicitly.

## Run

```bash
./factor.py --n /home/ubuntu/n.txt \
    --b1 3M --b2 10M \
    --devices 0,1,2 --threads 32 --waves 2
```

Useful options:

| option | meaning |
|---|---|
| `--n` | decimal/hex integer or path to a file |
| `--b1`, `--b2` | ECM bounds; accept `3000000`, `3M`, `1e7` |
| `--devices` | comma-separated GPU ids, or `all` |
| `--threads` / `--cpu-cores` | stage 2 CPU processes |
| `--waves` | ECM batches; each wave = `devices × curves` new curves; found factors are stripped between waves |
| `--curves` | curves per GPU per wave (default 4096; min useful ~1024) |
| `--trial-limit` | strip small prime factors up to this bound first (0=off) |
| `--maxmem` | stage 2 memory per process in MB (0 = gmp-ecm default) |
| `--seed` | reproducible sigma/shuffle seed |
| `--ecm` | override path to the `ecm` binary |
| `--stop-on-factor` | stop after the first wave that finds a factor |

Example with small-factor stripping:

```bash
./factor.py --n n.txt --b1 3M --b2 10M \
    --devices 0,1,2 --threads 32 --waves 4 --trial-limit 1000000
```

## How probability scales

Each wave adds `len(devices) * curves` independent ECM curves. The cumulative
probability for a factor with expected curve count `Nexp` is:

```
P(k waves) = 1 - exp(-k * curves_per_wave / Nexp)
```

`Nexp` depends on B1/B2 and factor size, not on the bit size of N. Larger N only
increases the cost per curve.

## Notes

- Stage 2 in this GMP-ECM fork is **CPU-only**. GPU memory is used only by
  stage 1; 24 GB is far more than needed (4096 curves at 2432 bits ≈ 6 MB).
- By default the driver runs all requested `--waves` and prints the divisors
  found after each wave (including "no divisors found"). At the end it prints
  the deduplicated total. Use `--stop-on-factor` for the old early-stop
  behavior.
- Factors found in a wave are divided out of N before the next wave, so later
  waves run on the reduced cofactor. Intermediate values are written to
  `n_wave_XX.txt` in the run directory.
- Stage 1 save files contain one line per curve, with independent sigma and
  residue, which is what makes the parallel stage 2 split valid.
