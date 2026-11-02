// g_eval.cpp -- see g_eval.h
#include "g_eval.h"
#include "g_coeffs.h"

#if G_COEFF_LANES != G_LANES
#error "g_coeffs.h was generated for a different lane count (tools/gen_coeffs.py --lanes)"
#endif

namespace {

union fbits {
    float f;
    uint32_t u;
};

inline uint32_t as_u32(float x) {
    fbits b;
    b.f = x;
    return b.u;
}

inline float as_f32(uint32_t u) {
    fbits b;
    b.u = u;
    return b.f;
}

// biased fp32 exponent field (0 for zero / denormal)
inline int exp_field(float x) {
#pragma HLS INLINE
    return (int)((as_u32(x) >> 23) & 0xff);
}

// x * 2^k by editing the exponent field; zero/denormal -> 0, underflow -> 0
inline float ldexp_f(float x, int k) {
#pragma HLS INLINE
    uint32_t u = as_u32(x);
    int ex = (int)((u >> 23) & 0xff);
    if (ex == 0) return 0.0f;
    int ne = ex + k;
    if (ne <= 0) return as_f32(u & 0x80000000u);
    if (ne >= 255) return as_f32((u & 0x80000000u) | 0x7f800000u);
    return as_f32((u & 0x807fffffu) | ((uint32_t)ne << 23));
}

// scale (re, im) so that max(|re|, |im|) lies in [1, 2); add the scale to e
inline void renorm(float &re, float &im, int32_t &e) {
#pragma HLS INLINE
    int er = exp_field(re);
    int ei = exp_field(im);
    int m = er > ei ? er : ei;
    if (m == 0) return;  // both zero
    int k = m - 127;
    re = ldexp_f(re, -k);
    im = ldexp_f(im, -k);
    e += k;
}

// 1/d for d in [1, 8) with multiplies and adds only (no divider IP): initial
// guess from the bit pattern (rel. error < 0.13), then 4 Newton steps
// r <- r (2 - d r), each squaring the error (-> fp32 rounding level)
inline float recip(float d) {
#pragma HLS INLINE
    float r = as_f32(0x7EF311C3u - as_u32(d));
RECIP:
    for (int i = 0; i < 4; i++) {
#pragma HLS UNROLL
        float t = d * r;
        r = r * (2.0f - t);
    }
    return r;
}

// (ar + i ai)(br + i bi): 4 fp32 multiplies + 2 fp32 adds -> DSPFP32
inline void cmul(float ar, float ai, float br, float bi, float &cr, float &ci) {
#pragma HLS INLINE
    float t1 = ar * br;
    float t2 = ai * bi;
    float t3 = ar * bi;
    float t4 = ai * br;
    cr = t1 - t2;
    ci = t3 + t4;
}

// prod_{j < n} (z - (ar[j] + i ai[j])) in block floating point, using G_LANES
// independent partial products (lane l takes factors l, l+L, l+2L, ...), so
// the loop-carried multiply latency is hidden; then the lanes are combined.
template <int NPAD>
void lane_product(float x, float y, const float ar[NPAD], const float ai[NPAD], int n,
                  float &out_r, float &out_i, int32_t &out_e) {
    float pr[G_LANES], pi[G_LANES];
    int32_t pe[G_LANES];
#pragma HLS ARRAY_PARTITION variable = pr complete
#pragma HLS ARRAY_PARTITION variable = pi complete
#pragma HLS ARRAY_PARTITION variable = pe complete
INIT:
    for (int l = 0; l < G_LANES; l++) {
#pragma HLS UNROLL
        pr[l] = 1.0f;
        pi[l] = 0.0f;
        pe[l] = 0;
    }
FACTORS:
    for (int j = 0; j < NPAD / G_LANES; j++) {
#pragma HLS PIPELINE
    LANES:
        for (int l = 0; l < G_LANES; l++) {
#pragma HLS UNROLL
            int idx = j * G_LANES + l;
            bool live = idx < n;
            float wr = live ? x - ar[idx] : 1.0f;
            float wi = live ? y - ai[idx] : 0.0f;
            float nr, ni;
            cmul(pr[l], pi[l], wr, wi, nr, ni);
            renorm(nr, ni, pe[l]);
            pr[l] = nr;
            pi[l] = ni;
        }
    }
    float cr = pr[0], ci = pi[0];
    int32_t ce = pe[0];
COMBINE:
    for (int l = 1; l < G_LANES; l++) {
        float nr, ni;
        cmul(cr, ci, pr[l], pi[l], nr, ni);
        ce += pe[l];
        renorm(nr, ni, ce);
        cr = nr;
        ci = ni;
    }
    out_r = cr;
    out_i = ci;
    out_e = ce;
}

inline void put_u32(hls::stream<uint8_t> &tx, uint32_t v, uint8_t &chk) {
#pragma HLS INLINE
    for (int i = 0; i < 4; i++) {
        uint8_t b = (uint8_t)(v >> (8 * i));
        tx.write(b);
        chk ^= b;
    }
}

}  // namespace

g_result g_eval(float x, float y) {
    // 8 coefficients per cycle from each ROM (one per lane)
#pragma HLS ARRAY_PARTITION variable = G_ZR cyclic factor = 8
#pragma HLS ARRAY_PARTITION variable = G_ZI cyclic factor = 8
#pragma HLS ARRAY_PARTITION variable = G_DR cyclic factor = 8
#pragma HLS ARRAY_PARTITION variable = G_DI cyclic factor = 8
    float nr, ni, dr, di;
    int32_t ne, de;
    lane_product<G_N_ZEROS_PAD>(x, y, G_ZR, G_ZI, G_N_ZEROS, nr, ni, ne);
    lane_product<G_N_DEN_PAD>(x, y, G_DR, G_DI, G_N_DEN, dr, di, de);

    g_result r;
    if (dr == 0.0f && di == 0.0f) {  // z is a pole
        r.re = as_f32(0x7fc00000u);
        r.im = as_f32(0x7fc00000u);
        r.e = 0;
        r.flags = G_FLAG_POLE;
        return r;
    }
    if (nr == 0.0f && ni == 0.0f) {  // z is a zero
        r.re = 0.0f;
        r.im = 0.0f;
        r.e = 0;
        r.flags = G_FLAG_ZERO | G_FLAG_INSIDE;
        return r;
    }
    // num / (c * den) = num * conj(den) / |den|^2 * (1/c);  |den|^2 in [1, 8)
    float d2 = dr * dr + di * di;
    float s = G_C_MANT_INV * recip(d2);
    float gr = (nr * dr + ni * di) * s;
    float gi = (ni * dr - nr * di) * s;
    int32_t e = ne - de - G_C_EXP;
    renorm(gr, gi, e);
    // |g| < 1  <=>  (gr^2 + gi^2) * 4^e < 1, with gr^2 + gi^2 in [1, 8)
    float m2 = gr * gr + gi * gi;
    bool inside = (e <= -2) || (e == -1 && m2 < 4.0f);
    r.re = gr;
    r.im = gi;
    r.e = e;
    r.flags = inside ? G_FLAG_INSIDE : 0;
    return r;
}

void g_uart_kernel(hls::stream<uint8_t> &rx, hls::stream<uint8_t> &tx) {
#pragma HLS INTERFACE mode = axis port = rx
#pragma HLS INTERFACE mode = axis port = tx
#pragma HLS INTERFACE mode = ap_ctrl_none port = return
    // wait for a request header
    uint8_t b = rx.read();
SYNC:
    while (b != G_SYNC_IN) b = rx.read();
    uint8_t p[8];
    uint8_t chk = 0;
PAYLOAD:
    for (int i = 0; i < 8; i++) {
        p[i] = rx.read();
        chk ^= p[i];
    }
    uint8_t got = rx.read();

    g_result r;
    if (got != chk) {
        r.re = 0.0f;
        r.im = 0.0f;
        r.e = 0;
        r.flags = G_FLAG_BADFRAME;
    } else {
        uint32_t xu = (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
        uint32_t yu = (uint32_t)p[4] | ((uint32_t)p[5] << 8) | ((uint32_t)p[6] << 16) | ((uint32_t)p[7] << 24);
        r = g_eval(as_f32(xu), as_f32(yu));
    }

    uint8_t ck = 0;
    tx.write(G_SYNC_OUT);
    put_u32(tx, as_u32(r.re), ck);
    put_u32(tx, as_u32(r.im), ck);
    put_u32(tx, (uint32_t)r.e, ck);
    tx.write(r.flags);
    ck ^= r.flags;
    tx.write(ck);
}
