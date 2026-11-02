#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

// Minimal self-contained SHA-256 (FIPS 180-4).
class Sha256 {
public:
    Sha256() { reset(); }

    void reset() {
        static constexpr std::uint32_t init[8] = {
            0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
            0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
        };
        std::memcpy(state_, init, sizeof(state_));
        buffer_len_ = 0;
        total_len_ = 0;
    }

    void update(const std::uint8_t *data, std::size_t len) {
        total_len_ += len;
        while (len > 0) {
            std::size_t take = 64 - buffer_len_;
            if (take > len) {
                take = len;
            }
            std::memcpy(buffer_ + buffer_len_, data, take);
            buffer_len_ += take;
            data += take;
            len -= take;
            if (buffer_len_ == 64) {
                transform(buffer_);
                buffer_len_ = 0;
            }
        }
    }

    void finish(std::uint8_t out[32]) {
        std::uint64_t bit_len = total_len_ * 8;
        std::uint8_t pad = 0x80;
        update(&pad, 1);
        std::uint8_t zero = 0;
        while (buffer_len_ != 56) {
            update(&zero, 1);
        }
        std::uint8_t len_be[8];
        for (int i = 0; i < 8; i++) {
            len_be[i] = static_cast<std::uint8_t>(bit_len >> (56 - 8 * i));
        }
        update(len_be, 8);
        for (int i = 0; i < 8; i++) {
            out[4 * i + 0] = static_cast<std::uint8_t>(state_[i] >> 24);
            out[4 * i + 1] = static_cast<std::uint8_t>(state_[i] >> 16);
            out[4 * i + 2] = static_cast<std::uint8_t>(state_[i] >> 8);
            out[4 * i + 3] = static_cast<std::uint8_t>(state_[i]);
        }
    }

private:
    static std::uint32_t rotr(std::uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

    void transform(const std::uint8_t block[64]) {
        static constexpr std::uint32_t K[64] = {
            0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5, 0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5,
            0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3, 0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174,
            0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC, 0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
            0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7, 0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967,
            0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13, 0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85,
            0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3, 0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
            0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5, 0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3,
            0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208, 0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
        };

        std::uint32_t w[64];
        for (int i = 0; i < 16; i++) {
            w[i] = (static_cast<std::uint32_t>(block[4 * i]) << 24) |
                   (static_cast<std::uint32_t>(block[4 * i + 1]) << 16) |
                   (static_cast<std::uint32_t>(block[4 * i + 2]) << 8) |
                   static_cast<std::uint32_t>(block[4 * i + 3]);
        }
        for (int i = 16; i < 64; i++) {
            std::uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            std::uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }

        std::uint32_t a = state_[0], b = state_[1], c = state_[2], d = state_[3];
        std::uint32_t e = state_[4], f = state_[5], g = state_[6], h = state_[7];
        for (int i = 0; i < 64; i++) {
            std::uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            std::uint32_t ch = (e & f) ^ (~e & g);
            std::uint32_t t1 = h + S1 + ch + K[i] + w[i];
            std::uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            std::uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
            std::uint32_t t2 = S0 + maj;
            h = g;
            g = f;
            f = e;
            e = d + t1;
            d = c;
            c = b;
            b = a;
            a = t1 + t2;
        }
        state_[0] += a;
        state_[1] += b;
        state_[2] += c;
        state_[3] += d;
        state_[4] += e;
        state_[5] += f;
        state_[6] += g;
        state_[7] += h;
    }

    std::uint32_t state_[8];
    std::uint8_t buffer_[64];
    std::size_t buffer_len_;
    std::uint64_t total_len_;
};
