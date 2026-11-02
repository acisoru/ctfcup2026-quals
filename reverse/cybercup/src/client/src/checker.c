#include <stddef.h>
#include <stdint.h>
#include "checker_constants.h"

static uint32_t rol(uint32_t x, unsigned n) { return (x << n) | (x >> (32 - n)); }
static uint32_t pack(const uint8_t *x) { return (uint32_t)x[0] | ((uint32_t)x[1] << 8) | ((uint32_t)x[2] << 16) | ((uint32_t)x[3] << 24); }

static void expand(uint8_t out[4][8], const uint8_t *bytes, size_t length, size_t chunk, uint32_t key, uint32_t salt, uint32_t mask) {
    for (size_t j = 0; j < 8; ++j) {
        size_t offset = chunk * 8 + j;
        uint8_t b = offset < length ? bytes[offset] : 0;
        uint8_t a = (uint8_t)(~b ^ (uint8_t)(key >> (8 * (j & 3))));
        uint8_t c = (uint8_t)(b + (uint8_t)(salt >> (8 * ((j + 1) & 3))));
        uint8_t d = (uint8_t)(a ^ c ^ (uint8_t)(mask >> (8 * ((j + 2) & 3))));
        out[0][j] = a;
        out[1][j] = c;
        out[2][j] = d;
        out[3][j] = (uint8_t)(d + b);
    }
}

static void hash_a(const uint8_t x[4][8], size_t index, uint32_t out[2]) {
    uint32_t left = UINT32_C(0x9E3779B9) ^ ((uint32_t)(index + 1) * UINT32_C(0x13579BDF));
    uint32_t right = UINT32_C(0x85EBCA6B) ^ ((uint32_t)(index + 1) * UINT32_C(0x27D4EB2D));
    for (size_t j = 0; j < 8; ++j) {
        uint32_t lane = x[0][j] + UINT32_C(0x101) + (uint32_t)j * UINT32_C(0x41);
        left = rol((left ^ lane) + right, (unsigned)(5 + j % 7));
        right = rol(right + (lane ^ left), (unsigned)(11 + j % 5)) ^ left;
    }
    out[0] = left; out[1] = right;
}

static void hash_b(const uint8_t x[4][8], size_t index, uint32_t out[2]) {
    uint32_t left = UINT32_C(0x9E3779B9) ^ ((uint32_t)(index + 1) * UINT32_C(0x13579BDF));
    uint32_t right = UINT32_C(0x85EBCA6B) ^ ((uint32_t)(index + 1) * UINT32_C(0x27D4EB2D));
    for (size_t j = 0; j < 6; ++j) {
        uint32_t lane = x[0][j] + UINT32_C(0x101) + (uint32_t)j * UINT32_C(0x41);
        right = rol((right ^ lane) + left, (unsigned)(7 + j % 9));
        left = rol(left + (lane ^ right), (unsigned)(11 + j % 7)) ^ right;
    }
    out[0] = left ^ pack(x[3] + 4); out[1] = right ^ pack(x[2]);
}

static void hash_c(const uint8_t x[4][8], size_t index, uint32_t out[2]) {
    uint32_t left = UINT32_C(0x9E3779B9) ^ ((uint32_t)(index + 1) * UINT32_C(0x13579BDF));
    uint32_t right = UINT32_C(0x85EBCA6B) ^ ((uint32_t)(index + 1) * UINT32_C(0x27D4EB2D));
    for (size_t j = 0; j < 4; ++j) {
        uint32_t lane = x[j & 1][j] + UINT32_C(0x101) + (uint32_t)j * UINT32_C(0x41);
        left = rol(left ^ (lane + right), (unsigned)(5 + j % 7));
    }
    for (size_t j = 4; j < 8; ++j) {
        uint32_t lane = x[j & 1][j] + UINT32_C(0x101) + (uint32_t)j * UINT32_C(0x41);
        right = rol(right + lane, (unsigned)(13 + j % 7)) ^ left;
    }
    out[0] = left ^ pack(x[3] + 4); out[1] = right ^ pack(x[2]);
}

static void hash_d(const uint8_t x[4][8], size_t index, uint32_t out[2]) {
    uint32_t left = UINT32_C(0x9E3779B9) ^ ((uint32_t)(index + 1) * UINT32_C(0x13579BDF));
    uint32_t right = UINT32_C(0x85EBCA6B) ^ ((uint32_t)(index + 1) * UINT32_C(0x27D4EB2D));
    for (size_t j = 0; j < 4; ++j) {
        uint32_t lane = x[1 - (j & 1)][j] + UINT32_C(0x101) + (uint32_t)j * UINT32_C(0x41);
        left = rol(left + lane, (unsigned)(9 + j % 7)) ^ (lane ^ right);
    }
    for (size_t j = 4; j < 8; ++j) {
        uint32_t lane = x[1 - (j & 1)][j] + UINT32_C(0x101) + (uint32_t)j * UINT32_C(0x41);
        right = rol(right ^ lane, (unsigned)(11 + j % 5)) + (lane ^ left);
    }
    out[0] = left ^ pack(x[3] + 4); out[1] = right ^ pack(x[2]);
}

int verify_flag(const uint8_t *bytes, size_t length) {
    if (!bytes || length != CHECKER_FLAG_LEN) return 0;
    uint8_t expanded[CHECKER_CHUNKS][4][8];
    uint32_t pairs[CHECKER_CHUNKS][2];
    uint32_t key = CHECKER_KEY_SEED, salt = CHECKER_SALT_SEED, mask = CHECKER_MASK_SEED;
    uint32_t route = UINT32_C(0x5A17D1E3), mismatch = 0;
    void (*hashes[4])(const uint8_t [4][8], size_t, uint32_t [2]) = {hash_a, hash_b, hash_c, hash_d};
    for (size_t i = 0; i < CHECKER_CHUNKS; ++i) {
        key = rol(key ^ CHECKER_KEY_XOR, 9) + CHECKER_KEY_ADD;
        salt = rol(salt + CHECKER_SALT_ADD, 13) ^ CHECKER_SALT_XOR;
        mask = rol(mask ^ CHECKER_MASK_XOR, 17) + CHECKER_MASK_ADD;
        expand(expanded[i], bytes, length, i, key, salt, mask);
        hashes[i & 3](expanded[i], i, pairs[i]);
        mismatch |= pairs[i][0] ^ CHECKER_CHUNK_TARGET_A[i];
        mismatch |= pairs[i][1] ^ CHECKER_CHUNK_TARGET_B[i];
        uint32_t mixed = pairs[i][0] ^ rol(pairs[i][1], 13) ^ ((uint32_t)(i + 1) * UINT32_C(0x9E3779B9));
        route = rol(route ^ mixed, (unsigned)(7 + i % 11)) + UINT32_C(0x7F4A7C15);
    }
    mismatch |= route ^ CHECKER_ROUTE_TARGET[0];
    uint32_t left = UINT32_C(0x243F6A88), right = UINT32_C(0x85A308D3);
    for (size_t i = 0; i < CHECKER_CHUNKS; ++i) {
        for (size_t lane = 0; lane < 4; ++lane) {
            uint32_t low = pack(expanded[i][lane]), high = pack(expanded[i][lane] + 4);
            left = rol((left ^ low) + right, (unsigned)(7 + (i + lane) % 9));
            right = rol((right + high) ^ left, (unsigned)(11 + (i + lane) % 7)) + low;
        }
    }
    mismatch |= left ^ CHECKER_GLOBAL_TARGET[0];
    mismatch |= right ^ CHECKER_GLOBAL_TARGET[1];
    return mismatch == 0;
}
