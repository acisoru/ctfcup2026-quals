// tb_g_eval.cpp -- C testbench (Vitis HLS csim / cosim, or plain g++):
// drives the UART byte protocol of g_uart_kernel with the generated test
// vectors and compares every reply with g computed in double precision.
#include <cmath>
#include <cstdio>
#include <cstring>

#include "g_eval.h"
#include "test_vectors.h"

static void send_request(hls::stream<uint8_t> &rx, float x, float y, bool corrupt) {
    uint8_t p[8];
    std::memcpy(p, &x, 4);
    std::memcpy(p + 4, &y, 4);
    uint8_t chk = 0;
    rx.write(G_SYNC_IN);
    for (int i = 0; i < 8; i++) {
        rx.write(p[i]);
        chk ^= p[i];
    }
    rx.write(corrupt ? (uint8_t)(chk ^ 0x55) : chk);
}

static bool read_reply(hls::stream<uint8_t> &tx, g_result &r) {
    uint8_t b[15];
    for (int i = 0; i < 15; i++) b[i] = tx.read();
    if (b[0] != G_SYNC_OUT) return false;
    uint8_t ck = 0;
    for (int i = 1; i < 14; i++) ck ^= b[i];
    if (ck != b[14]) return false;
    std::memcpy(&r.re, b + 1, 4);
    std::memcpy(&r.im, b + 5, 4);
    std::memcpy(&r.e, b + 9, 4);
    r.flags = b[13];
    return true;
}

int main() {
    hls::stream<uint8_t> rx("rx"), tx("tx");
    int fails = 0, near_boundary_flips = 0, checked = 0;
    double max_dlog = 0, max_darg = 0, worst_flip = 0;

    for (int i = 0; i < TV_N; i++) {
        // some line noise before a few requests: the kernel must resync
        if (i % 97 == 5) {
            rx.write(0x00);
            rx.write(0x5A);
            rx.write(0x13);
        }
        send_request(rx, TV_X[i], TV_Y[i], false);
        g_uart_kernel(rx, tx);
        g_result r;
        if (!read_reply(tx, r)) {
            std::printf("vector %d: malformed reply\n", i);
            fails++;
            continue;
        }
        double ref = TV_LOG2ABS[i];
        if (ref < -1e299) {  // exact zero of g
            if (!(r.flags & G_FLAG_ZERO)) {
                std::printf("vector %d: expected a zero, flags %02x\n", i, r.flags);
                fails++;
            }
            continue;
        }
        if (ref > 1e299) {  // exact pole of g
            if (!(r.flags & G_FLAG_POLE) || !std::isnan(r.re)) {
                std::printf("vector %d: expected a pole, flags %02x\n", i, r.flags);
                fails++;
            }
            continue;
        }
        checked++;
        double m = std::hypot((double)r.re, (double)r.im);
        double hw_log2 = r.e + std::log2(m);
        double hw_arg = std::atan2((double)r.im, (double)r.re);
        double dlog = std::fabs(hw_log2 - ref);
        double darg = std::fabs(std::remainder(hw_arg - TV_ARG[i], 2 * M_PI));
        if (dlog > max_dlog) max_dlog = dlog;
        if (darg > max_darg) max_darg = darg;
        bool ref_inside = ref < 0;
        bool hw_inside = r.flags & G_FLAG_INSIDE;
        if (ref_inside != hw_inside) {
            // only acceptable when g is within rounding of the outline |g| = 1
            if (std::fabs(ref) < 1e-3) {
                near_boundary_flips++;
                if (std::fabs(ref) > worst_flip) worst_flip = std::fabs(ref);
            } else {
                std::printf("vector %d (%g, %g): inside flag %d, reference log2|g| = %g\n", i, TV_X[i], TV_Y[i], hw_inside, ref);
                fails++;
            }
        }
        if (dlog > 1e-3 || darg > 1e-3) {
            std::printf("vector %d (%g, %g): log2|g| hw %.9g ref %.9g, arg err %.3g\n", i, TV_X[i], TV_Y[i], hw_log2, ref, darg);
            fails++;
        }
    }

    // a corrupted request must be answered with the bad-frame flag
    send_request(rx, 1.0f, 0.25f, true);
    g_uart_kernel(rx, tx);
    g_result r;
    if (!read_reply(tx, r) || r.flags != G_FLAG_BADFRAME) {
        std::printf("corrupted request not flagged\n");
        fails++;
    }

    std::printf("checked %d finite values (+ zero, pole, bad frame):\n", checked);
    std::printf("  max |log2|g| error| = %.3g  (bits of magnitude)\n", max_dlog);
    std::printf("  max |arg g error|   = %.3g rad\n", max_darg);
    std::printf("  inside/outside flips within 1e-3 of |g| = 1: %d (largest |log2|g|| %.2g)\n", near_boundary_flips, worst_flip);
    std::printf("%s (%d failures)\n", fails ? "FAIL" : "PASS", fails);
    return fails ? 1 : 0;
}
