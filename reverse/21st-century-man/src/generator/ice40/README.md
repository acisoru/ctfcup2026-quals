# g(x, y) on an iCE40 over UART, and back to C++

Open-toolchain build of the text-function evaluator (the same device as
`../dsp58`, same byte protocol), plus the way back: the bitstream is unpacked
into a netlist, compiled to C++ and run as a serial device on a pseudo-terminal.

```text
 text_lemniscate --> model/flag_raw.json --scale_model.py--> model/flag.json
                                  |
 model/flag.json --gen_rom.py--> gen/rom.hex, orders.vh, params.vh, vectors.txt
                                  |
   rtl/*.v  --yosys--> build/g.json --nextpnr-ice40--> build/g.asc --icepack--> build/g.bin
                                                                                   |
  build/g.bin --iceunpack--> design.asc --icebox_vlog--> design.v --yosys write_cxxrtl--> design.cc
                                                                                   |
                                      sim/device_main.cc + design.cc --g++--> ./device  (pty)
```

Everything runs inside a Docker image (`Dockerfile`: Debian + a pinned YosysHQ
OSS CAD Suite release with yosys, nextpnr-ice40, icestorm, iverilog, verilator).
`make` builds the image on first use. `make NATIVE=1 ...` uses tools from `$PATH`.

## Build

```sh
make                                   # -> build/g.bin  (CLK_MHZ=200 BAUD=921600 UP5K/SG48 by default)
make CLK_MHZ=200 BAUD=921600 DEVICE=up5k PACKAGE=sg48 MODEL_RAW=model/flag_raw.json
make DEVICE=hx8k PACKAGE=ct256         # the other supported part (pcf/hx8k_ct256.pcf)
make sim                               # RTL regression, iverilog, every 7th of 3000 reference points
```

The model is the flag text, made with the generator in `../lemniscate`:

```sh
text_lemniscate build 'ctfcup{3ab5e98041a0f89b67273ba39b17b37a}' -d 2940 --holes keep --spacing 0.3 \
    --no-map --model model/flag_raw.json
```

39 glyphs need a high degree; `--holes keep` leaves the counters as holes (one
pole each) instead of slitting them open, which is what keeps the letters
readable with ~75 zeros per glyph (`model/flag_preview.png` is |g| < 1 of the
final model). `tools/scale_model.py` then scales the text into the evaluator's
[-4, 4) range (the raw text is 39 units wide) and rounds every zero and pole to
a multiple of 2^-12, the resolution of the ROM, so that `model/flag.json` is
exactly the function the hardware computes.

| step | tool | output |
|---|---|---|
| model | `tools/scale_model.py` | `model/flag.json` (2940 zeros, 377 poles of total order 2292, box [-3.9, 3.9] x [-0.1275, 0.1275]) |
| tables | `tools/gen_rom.py` | `gen/rom.hex` (block-RAM image), `gen/orders.vh`, `gen/params.vh`, `gen/vectors.txt` |
| synthesis | `yosys synth_ice40` | `build/g.json` (~4200 LUT4, 29 block RAMs) |
| place & route | `nextpnr-ice40 --up5k` | `build/g.asc` (96 % of the LCs and 29/30 block RAMs of a UP5K) |
| bitstream | `icepack` | `build/g.bin` (the "binary stream", 104 kB) |

`CLK_MHZ` and `BAUD` only set the UART bit period (`CLK_MHZ*1e6/BAUD` clocks per
bit, 217 for the defaults); the arithmetic is clock-agnostic. The design closes
timing at about 7 MHz on a UP5K, far from 200 MHz, so place & route runs with
`--timing-allow-fail`. The bitstream is meant to be simulated, not flashed; on a
real board the same `.bin` works at any clock with a matching baud rate.

## Bitstream -> C++ -> device

```sh
make cxx          # tools/bitstream2cxx.sh build/g.bin build/cxx   (~1 min)
make device       # tools/run_device.sh build/cxx: compiles (several minutes) and runs
```

`tools/bitstream2cxx.sh bitstream.bin out_dir [-p pins.pcf]` writes:

* `out_dir/design.asc` — the unpacked configuration (`iceunpack`),
* `out_dir/design.v` — a Verilog netlist of the chip (`icebox_vlog`): every LUT
  as an `assign`, every flip-flop as an `always`, the 29 `SB_RAM40_4K` blocks
  with their `INIT_*` contents, i.e. the coefficient ROM,
* `out_dir/design.cc`, `design.h` — the chip as a C++ class (yosys `write_cxxrtl`
  over the netlist plus yosys' own `ice40/cells_sim.v` models), plus the `cxxrtl/`
  runtime headers, so the directory is self-contained.

One yosys quirk is worked around in the script: a memory write port with a
constant clock (the ROMs' unused write side) crashes `write_cxxrtl`, so `opt_mem`
runs first and deletes those never-enabled ports.

The pin names come from the pcf (`clk`, `uart_rxd`, `uart_txd`); without `-p` the
pcf matching the device in the bitstream is picked from `pcf/`.

`tools/run_device.sh [-c CLK_HZ] [-b BAUD] [-l link] [-s] out_dir` compiles
`sim/device_main.cc` with the generated C++ and runs it. The harness clocks the
model, bit-bangs the UART pins with the real bit period and connects them to a
pty whose path it prints (and symlinks to `-l link`); `-s` uses stdin/stdout
instead, like `dsp58/build/g_uart_emulator`. Any serial client works:

```sh
make device &                                            # prints /dev/pts/N, symlink build/g_uart
python3 ../dsp58/host/g_client.py --port build/g_uart --baud 921600 --timeout 60 --at 0,0
python3 ../dsp58/host/g_client.py --port build/g_uart --baud 921600 --timeout 60 --scan model/flag.json
make check                                               # 200 random points vs double precision
cargo run --manifest-path ../../problem/Cargo.toml -- --port build/g_uart       # the drawing checker
```

The model is gate-level (every LUT of the chip is evaluated every clock), so one
evaluation takes about 3 s of host time (5200 factors, ~190 000 clocks); the
host harness blocks instead of spinning while the device is idle. The compile
takes about a minute (`-Ofast`; `CXXFLAGS` overrides it); the binary is cached
in `build/cxx/device`. Give clients a generous reply timeout (`g_client.py
--timeout 60`; the drawing checker defaults to 60 s).

## Protocol

Identical to `../dsp58` (little endian, fp32 / int32, 8N1):

```text
request  A5 | x[4] | y[4] | xor(x,y bytes)                           10 bytes
reply    5A | re[4] | im[4] | e[4] | flags | xor(bytes 1..13)        15 bytes
g(x + iy) = (re + i*im) * 2^e,  max(|re|, |im|) in [1, 2)
flags: 0x01 |g| < 1   0x02 pole (re = im = NaN)   0x04 zero   0x80 bad request checksum
```

## How the evaluator computes (rtl/g_kernel.v)

No floating-point units; the iCE40 has none and the DSP58 design's fp32 pipeline
would not fit. Instead:

* coordinates are signed Q4.28 fixed point, inputs saturated to [-4, 4); the
  coefficients are stored as Q4.12 (16 bits, the model is quantised to that),
  so every difference `z - a_j` is exact;
* a running product is a complex block-floating-point number
  `(re, im) * 2^e` with Q2.30 mantissas, `max(|re|, |im|)` in [1, 2);
  one complex multiply = four 32x32 shift-add multipliers in parallel
  (32 clocks), then a leading-one detector and a shifter renormalise;
* numerator (2940 zeros) and denominator (377 poles with multiplicities, 2292
  factors) are formed this way, then `g = N conj(D) / |D|^2 / c`, with the
  reciprocal from a 61-clock restoring divider;
* `|g| < 1  <=>  e <= -2 or (e == -1 and re^2 + im^2 < 4)`.

About 190 000 clocks per evaluation. Measured against the double-precision
reference at the same fixed-point inputs/coefficients (`make sim`): max error
6e-7 in log2|g|, no inside/outside disagreements, exact zero and pole detected,
corrupted request answered with flag 0x80.

The 2940 zeros + 377 poles live in `gen/rom.hex`, one 32-bit word `{im, re}`
(Q4.12 each) per point -> 26 block RAMs in 13 groups of two (256 x 16 each; the
other 3 are the UART FIFOs); the pole orders are a small logic table. All of it
is recoverable from the bitstream (`design.v` carries the `INIT_*` parameters;
inside a BRAM the 16 bits of a word sit in bit-reversed order, the iCE40's
physical column order). `../../../solve/solve.py` does that.

## Layout

```text
Dockerfile              builder image (OSS CAD Suite pinned by date)
Makefile                the flow; CLK_MHZ BAUD DEVICE PACKAGE MODEL_RAW MODEL NATIVE
model/flag_raw.json     text_lemniscate output for the flag text; flag.json: scaled + quantised;
                        flag_preview.png: |g| < 1 of flag.json
rtl/g_top.v             chip top: power-on reset, uart_rx -> fifo -> g_kernel -> fifo -> uart_tx
rtl/g_kernel.v          the evaluator + UART framing (+ cmul4, recip30)
rtl/uart_rx.v uart_tx.v axis_fifo.v   from ../dsp58/rtl
pcf/                    pin constraints: up5k_sg48 (iCEBreaker), hx8k_ct256
tools/scale_model.py    raw model -> scaled into [-4, 4), coefficients rounded to 2^-12
tools/gen_rom.py        model.json -> gen/
tools/bitstream2cxx.sh  bitstream -> design.asc / design.v / design.cc
tools/run_device.sh     design.cc + harness -> ./device on a pty
sim/tb_top.v            UART-level testbench against gen/vectors.txt
sim/device_main.cc      the UART <-> pty harness
```
