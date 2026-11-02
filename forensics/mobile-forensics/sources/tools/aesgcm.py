"""Pure-stdlib AES-256-GCM reference implementation for Burnt Note.

Used by both the evidence generator and the author's solver, so both sides
share byte-identical crypto. Verifies itself against NIST GCM Test Case 16
on import when selftest() is called.
"""

import hmac as _hmac

# ---------------------------------------------------------------------------
# GF(2^8) / S-box tables (generated, no magic constants to mistype)
# ---------------------------------------------------------------------------

def _make_tables():
    exp = [0] * 256
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        # multiply by the generator 0x03 (0x02 is NOT primitive here:
        # its multiplicative order is only 51)
        xt = x << 1
        if xt & 0x100:
            xt ^= 0x11B
        x ^= xt
    sbox = [0] * 256
    inv_sbox = [0] * 256
    for a in range(256):
        b = exp[(255 - log[a]) % 255] if a else 0
        s = (b ^ ((b << 1) | (b >> 7)) ^ ((b << 2) | (b >> 6))
             ^ ((b << 3) | (b >> 5)) ^ ((b << 4) | (b >> 4)) ^ 0x63) & 0xFF
        sbox[a] = s
        inv_sbox[s] = a
    return sbox, inv_sbox

_SBOX, _INV_SBOX = _make_tables()

_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _xtime(a):
    a <<= 1
    if a & 0x100:
        a ^= 0x11B
    return a


def _key_expansion_256(key):
    assert len(key) == 32
    words = [list(key[4 * i:4 * i + 4]) for i in range(8)]
    for i in range(8, 60):
        temp = list(words[i - 1])
        if i % 8 == 0:
            temp = temp[1:] + temp[:1]           # RotWord
            temp = [_SBOX[b] for b in temp]      # SubWord
            temp[0] ^= _RCON[i // 8 - 1]
        elif i % 8 == 4:
            temp = [_SBOX[b] for b in temp]
        words.append([words[i - 8][j] ^ temp[j] for j in range(4)])
    return words


def _encrypt_block(words, block):
    # state[column][row], AES lays out column-major
    s = [[block[r + 4 * c] for r in range(4)] for c in range(4)]

    def add_round_key(rnd):
        for c in range(4):
            w = words[4 * rnd + c]
            for r in range(4):
                s[c][r] ^= w[r]

    def shift_rows():
        for r in range(1, 4):
            row = [s[c][r] for c in range(4)]
            for c in range(4):
                s[c][r] = row[(c + r) % 4]

    def mix_columns():
        for c in range(4):
            a = [s[c][r] for r in range(4)]
            s[c][0] = _xtime(a[0]) ^ _xtime(a[1]) ^ a[1] ^ a[2] ^ a[3]
            s[c][1] = a[0] ^ _xtime(a[1]) ^ _xtime(a[2]) ^ a[2] ^ a[3]
            s[c][2] = a[0] ^ a[1] ^ _xtime(a[2]) ^ _xtime(a[3]) ^ a[3]
            s[c][3] = _xtime(a[0]) ^ a[0] ^ a[1] ^ a[2] ^ _xtime(a[3])

    add_round_key(0)
    for rnd in range(1, 14):
        for c in range(4):
            for r in range(4):
                s[c][r] = _SBOX[s[c][r]]
        shift_rows()
        mix_columns()
        add_round_key(rnd)
    for c in range(4):
        for r in range(4):
            s[c][r] = _SBOX[s[c][r]]
    shift_rows()
    add_round_key(14)
    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[r + 4 * c] = s[c][r]
    return bytes(out)


# ---------------------------------------------------------------------------
# GCM
# ---------------------------------------------------------------------------

# Reflected GF(2^128) multiplication exactly as SP 800-38D Algorithm 1:
# within a 128-bit block read as a big-endian integer, bit 127 of the int
# (leftmost bit) is the coefficient of x^0; R = 11100001 || 0^120.
_R = 0xE1 << 120


def _gf_mult(x, y):
    z = 0
    v = x
    for i in range(128):
        # selector bits run from the LEFTMOST bit (spec's X_0) while v
        # walks the powers x^0, x^1, ... via right shifts
        if (y >> (127 - i)) & 1:
            z ^= v
        if v & 1:
            v = (v >> 1) ^ _R
        else:
            v >>= 1
    return z


def _to_int(b):
    return int.from_bytes(b, "big")


def _ghash(h_int, aad, ct):
    def blocks(data):
        for i in range(0, len(data), 16):
            yield data[i:i + 16]
    y = 0
    for blk in blocks(aad + b"\x00" * ((16 - len(aad) % 16) % 16)):
        y = _gf_mult(y ^ _to_int(blk), h_int)
    for blk in blocks(ct + b"\x00" * ((16 - len(ct) % 16) % 16)):
        y = _gf_mult(y ^ _to_int(blk), h_int)
    lenblk = ((len(aad) * 8) << 64) | (len(ct) * 8)
    y = _gf_mult(y ^ lenblk, h_int)
    return y.to_bytes(16, "big")


def _aes_ecb_block(key, block):
    return _encrypt_block(_key_expansion_256(key), block)


def _ctr_xor(key, j0, data):
    out = bytearray()
    counter_hi = j0[:12]
    counter_lo = int.from_bytes(j0[12:], "big")
    for i in range(0, len(data), 16):
        ctr = counter_hi + ((counter_lo + 1 + i // 16) & 0xFFFFFFFF).to_bytes(4, "big")
        ks = _aes_ecb_block(key, ctr)
        chunk = data[i:i + 16]
        out.extend(b ^ k for b, k in zip(chunk, ks))
    return bytes(out)


def gcm_encrypt(key, nonce, aad, plaintext):
    assert len(key) == 32 and len(nonce) == 12
    h = _aes_ecb_block(key, b"\x00" * 16)
    j0 = nonce + b"\x00\x00\x00\x01"
    ct = _ctr_xor(key, j0, plaintext)
    tag = bytes(a ^ b for a, b in zip(_aes_ecb_block(key, j0),
                                      _ghash(_to_int(h), aad, ct)))
    return ct + tag


def gcm_decrypt(key, nonce, aad, frame):
    assert len(key) == 32 and len(nonce) == 12
    ct, tag = frame[:-16], frame[-16:]
    h = _aes_ecb_block(key, b"\x00" * 16)
    j0 = nonce + b"\x00\x00\x00\x01"
    expect = bytes(a ^ b for a, b in zip(_aes_ecb_block(key, j0),
                                         _ghash(_to_int(h), aad, ct)))
    if not _hmac.compare_digest(expect, tag):
        raise ValueError("GCM tag mismatch")
    return _ctr_xor(key, j0, ct)


def selftest():
    # NIST SP 800-38D / csrc.nist.gov AES_GCM.txt, GCM-AES256 Example #2:
    # empty AAD, 64-byte PT. Also validates the documented intermediates
    # H, J0-encryption and the GHASH output S.
    key = bytes.fromhex(
        "feffe9928665731c6d6a8f9467308308"
        "feffe9928665731c6d6a8f9467308308")
    iv = bytes.fromhex("cafebabefacedbaddecaf888")
    pt = bytes.fromhex(
        "d9313225f88406e5a55909c5aff5269a"
        "86a7a9531534f7da2e4c303d8a318a72"
        "1c3c0c95956809532fcf0e2449a6b525"
        "b16aedf5aa0de657ba637b391aafd255")
    aad = b""
    h = _aes_ecb_block(key, b"\x00" * 16)
    assert h.hex() == "acbef20579b4b8ebce889bac8732dad7", "H mismatch"
    frame = gcm_encrypt(key, iv, aad, pt)
    assert len(frame) == 64 + 16
    assert frame[:-16].hex() == (
        "522dc1f099567d07f47f37a32a84427d"
        "643a8cdcbfe5c0c97598a2bd2555d1aa"
        "8cb08e48590dbb3da7b08b1056828838"
        "c5f61e6393ba7a0abcc9f662898015ad"), "CT mismatch"
    assert _ghash(int.from_bytes(h, "big"), aad, frame[:-16]).hex() == \
        "4db870d37cb75fcb46097c36230d1612", "GHASH S mismatch"
    assert frame[-16:].hex() == "b094dac5d93471bdec1a502270e3cc6c", "tag mismatch"
    assert gcm_decrypt(key, iv, aad, frame) == pt
    # tamper detection
    bad = bytearray(frame)
    bad[0] ^= 1
    try:
        gcm_decrypt(key, iv, aad, bytes(bad))
        raise AssertionError("tampered frame passed")
    except ValueError:
        pass
    return True


if __name__ == "__main__":
    selftest()
    print("AES-256-GCM selftest OK")
