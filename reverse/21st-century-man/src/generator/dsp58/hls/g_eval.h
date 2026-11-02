// g_eval.h -- evaluator for the text function g on Xilinx Versal (DSP58 / DSPFP32)
//
//   g(z) = prod_j (z - a_j) / ( c * prod_k (z - b_k) ),   z = x + i y
//
// The coefficients come from g_coeffs.h (tools/gen_coeffs.py).  A direct fp32
// product of ~1500 factors would overflow after ~50 terms, so every running
// product is kept in block floating point: (re + i im) * 2^e with
// max(|re|,|im|) in [1, 2), renormalised after each complex multiply by
// adjusting the fp32 exponent fields (fabric logic, no DSP).  The complex
// multiplies, adds and subtracts are fp32 and map onto DSP58 slices in DSPFP32
// mode (see run_hls.tcl: config_op ... -impl primitivedsp).
//
// UART byte protocol (little endian, IEEE-754 fp32):
//   request : 0xA5, x[4], y[4], xor(x[4], y[4])                         10 bytes
//   reply   : 0x5A, re[4], im[4], e[4] (int32), flags, xor(bytes 1..13)  15 bytes
//   g(x + iy) = (re + i im) * 2^e
//   flags   : bit0 |g| < 1 (inside the smoothed text)
//             bit1 pole (g infinite; re = im = NaN)
//             bit2 g = 0 (z is a zero of g)
//             bit7 bad request checksum (no evaluation)
#pragma once
#include <stdint.h>
#include "hls_stream.h"

#define G_LANES 8          // interleaved partial products (8 complex multipliers)
#define G_SYNC_IN 0xA5
#define G_SYNC_OUT 0x5A
#define G_FLAG_INSIDE 0x01
#define G_FLAG_POLE 0x02
#define G_FLAG_ZERO 0x04
#define G_FLAG_BADFRAME 0x80

struct g_result {
    float re;       // g = (re + i im) * 2^e,  max(|re|,|im|) in [1, 2)
    float im;
    int32_t e;
    uint8_t flags;
};

// evaluate g at x + i y
g_result g_eval(float x, float y);

// top-level kernel: one request in, one reply out per invocation (free running)
void g_uart_kernel(hls::stream<uint8_t> &rx, hls::stream<uint8_t> &tx);
