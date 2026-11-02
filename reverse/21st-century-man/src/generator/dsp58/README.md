# g(x, y) on Xilinx Versal (DSP58) over UART

FPGA design that listens on a UART for `x, y` and answers with `g(x + iy)`, where

```text
g(z) = prod_j (z - a_j) / ( c * prod_k (z - b_k)^m_k )
```

is the text function built by `text_lemniscate build --model model.json`
(|g| < 1 on the smoothed text, |g| > 1 on the rest of the box/circle, poles at a few points).

## Layout

```text
model/hello.json        model from the Rust tool ("Hello", degree 1500, 33 poles)
tools/gen_coeffs.py     model.json -> hls/g_coeffs.h (fp32 ROMs) + hls/test_vectors.h
hls/g_eval.{h,cpp}      the evaluator + UART framing (Vitis HLS C++)
hls/tb_g_eval.cpp       C testbench: 3000 points vs double-precision reference
hls/g_uart_emulator.cpp the kernel as a desktop program on stdin/stdout
rtl/                    uart_rx, uart_tx, axis_fifo, g_uart_top, system_top (CIPS clock/reset)
rtl/sim/                kernel stand-in + Icarus testbench of the UART plumbing
constraints/uart_pins.xdc   the two UART pins -- set them for your board
build/Makefile          the flow (hls.tcl, synth.tcl, cips_bd.tcl, pnr.tcl, image.tcl)
host/g_client.py        pyserial client (also drives the emulator)
```

## Build

```sh
cd build
make                      # vitis-run (HLS) -> synth.dcp -> routed.dcp -> firmware.pdi
make PART=xcve2802-vsvh1760-2MP-e-S CLK_MHZ=200 BAUD=921600   # other device / clock / baud
make MODEL=../model/other.json      # new text: regenerates the ROMs first
make csim                 # C model vs reference (g++ only)
make sim                  # UART RTL simulation (iverilog)
make emulator             # desktop emulator for host/g_client.py
make clean
```

| stage | tool | output |
|---|---|---|
| ROMs | `tools/gen_coeffs.py` | `hls/g_coeffs.h` |
| HLS | `vitis-run --mode hls --tcl hls.tcl` (older: `HLS="vitis_hls -f"`) | `g_hls/sol1/impl/ip` |
| synthesis | `vivado -source synth.tcl` | `synth.dcp` |
| place & route | `vivado -source pnr.tcl` | `routed.dcp` |
| device image | `vivado -source image.tcl` | `firmware.pdi` |

Defaults: `PART=xcvc1902-vsva2197-2MP-e-S` (VCK190), 250 MHz PL clock from the CIPS,
115200 baud. **Set the two UART pins in `constraints/uart_pins.xdc` first**; place & route
stops with a message until they are set. Program with Vivado Hardware Manager or
`program_device` using `firmware.pdi`.

## Protocol

Little endian, IEEE-754 fp32 / int32, 8N1.

```text
request  A5 | x[4] | y[4] | xor(x,y bytes)                           10 bytes
reply    5A | re[4] | im[4] | e[4] | flags | xor(bytes 1..13)        15 bytes

g(x + iy) = (re + i*im) * 2^e,   max(|re|, |im|) in [1, 2)
flags: 0x01 |g| < 1 (inside the smoothed text)   0x02 pole (re = im = NaN)
       0x04 g = 0 (a zero)                       0x80 bad request checksum
```

g spans hundreds of orders of magnitude over the box (2^-15 inside a letter, 2^271 at its
edge), so the reply carries its own exponent instead of a plain float.

```sh
python3 host/g_client.py --port /dev/ttyUSB0 --at 0.3,0.4
python3 host/g_client.py --port /dev/ttyUSB0 --scan model/hello.json     # ASCII picture of the inside flag
python3 host/g_client.py --port /dev/ttyUSB0 --check model/hello.json    # vs double precision
python3 host/g_client.py --emulator build/g_uart_emulator --scan model/hello.json   # no board
```

## How it computes

* **fp32 on DSP58.** All multiplies and adds are fp32 and are mapped to DSP58 slices in
  DSPFP32 mode (`config_op ... -impl primitivedsp` in `hls.tcl`). The one division is
  replaced by a bit-pattern initial guess and 4 Newton steps, so there is no divider IP.
* **Block floating point.** A plain fp32 product of 1500 factors overflows after about 50
  terms. Each running product is kept as (re + i·im)·2^e and renormalised after every
  complex multiply by editing exponent fields, which is fabric logic, not DSP.
* **8 lanes.** Factors are spread over 8 interleaved partial products (8 complex
  multipliers), which hides the multiply–add latency of the product recurrence. Numerator
  (1500 zeros) and denominator (526 pole factors) are then combined, divided, and scaled by 1/c.
* **Inside flag.** |g| < 1 ⇔ (re² + im²)·4^e < 1, decided exactly from the normalised form.

## Verified here vs. not

* `make csim`: 3000 points (grid, random, ±0.002 from the outline, an exact zero, an exact
  pole) vs double precision at the same fp32 inputs and coefficients: max error 2.9e-5 bits
  in |g|, 9e-6 rad in arg g, **0 inside/outside disagreements**. Line noise and a corrupted
  request are also handled.
* `make sim`: UART RX/TX, FIFOs and back-pressure with a kernel stand-in: 3 requests,
  45 reply bytes, all correct.
* Emulator + host client: same kernel code over the byte protocol; `--scan` draws the text.
* **Not run here:** Vitis HLS, Vivado, hardware. The HLS pragmas, the CIPS configuration
  keys in `cips_bd.tcl` and the IP names follow the AMD tools' documented conventions but are
  untested. Expect to adjust `cips_bd.tcl` (or create the CIPS once in IP integrator) for
  your Vivado version and board.

Rough, unsynthesised estimate: about 130–150 DSP58 (8 lanes × 2 products), a few thousand
cycles per evaluation (≈10–15 µs at 250 MHz). The UART dominates: 25 bytes per evaluation,
about 450 evaluations/s at 115200 baud or 3600/s at 921600.
