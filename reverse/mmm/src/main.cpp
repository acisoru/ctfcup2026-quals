#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

#include "params.h"
#include "sha256.h"

// Multiply the byte vector by MATRIX and check whether the result is
// collinear with the input, i.e. the input is an eigenvector of MATRIX.
bool check(const char *s) {
    if (std::strlen(s) != N) {
        return false;
    }

    std::vector<std::int64_t> v(N);
    for (std::size_t i = 0; i < N; i++) {
        v[i] = static_cast<unsigned char>(s[i]);
    }

    std::vector<std::int64_t> y(N, 0);
    for (std::size_t i = 0; i < N; i++) {
        for (std::size_t j = 0; j < N; j++) {
            y[i] += MATRIX[i][j] * v[j];
        }
    }

    // y and v are collinear iff all 2x2 minors vanish: y[i]*v[j] == y[j]*v[i].
    bool nonzero = false;
    for (std::size_t i = 0; i < N; i++) {
        nonzero |= y[i] != 0;
        for (std::size_t j = i + 1; j < N; j++) {
            if (y[i] * v[j] != y[j] * v[i]) {
                return false;
            }
        }
    }
    return nonzero;
}

// SHA-256 of the input must match the stored digest.
bool hash_check(const char *s) {
    Sha256 ctx;
    ctx.update(reinterpret_cast<const std::uint8_t *>(s), std::strlen(s));
    std::uint8_t digest[32];
    ctx.finish(digest);
    return std::memcmp(digest, FLAG_HASH, sizeof(digest)) == 0;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        std::printf("usage: %s <offering>\n", argv[0]);
        return 1;
    }

    if (!check(argv[1])) {
        std::puts("The mirror shows a stranger. Walk the same line as the glass, and it may remember you.");
        return 1;
    }

    if (!hash_check(argv[1])) {
        std::puts("Your shadow falls where it should, yet the seal does not know your name.");
        return 1;
    }

    std::puts("The seal breaks. Carry what you brought to the gate.");
    return 0;
}
