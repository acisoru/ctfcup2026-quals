"""VRF dice prediction (the exploit payload), matching VRF.sol / the daemon.

Includes a pure-Python Keccak-256 (Ethereum keccak, NOT SHA3) so there are no
third-party crypto dependencies. Given the recovered secret s, predicts every
ply's dice for any (gameId, turn).
"""

# ------------------------------------------------------------ Keccak-256

_KECCAK_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_KECCAK_ROT = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]
_MASK = (1 << 64) - 1


def _rotl(x, n):
    return ((x << n) | (x >> (64 - n))) & _MASK


def _keccak_f(state):
    A = [[state[x + 5 * y] for y in range(5)] for x in range(5)]
    for rnd in range(24):
        # theta
        C = [A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4] for x in range(5)]
        D = [C[(x - 1) % 5] ^ _rotl(C[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                A[x][y] ^= D[x]
        # rho + pi
        B = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                B[y][(2 * x + 3 * y) % 5] = _rotl(A[x][y], _KECCAK_ROT[x][y])
        # chi
        for x in range(5):
            for y in range(5):
                A[x][y] = B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y])
        # iota
        A[0][0] ^= _KECCAK_RC[rnd]
    out = [0] * 25
    for x in range(5):
        for y in range(5):
            out[x + 5 * y] = A[x][y]
    return out


def keccak256(data: bytes) -> bytes:
    rate = 136  # bytes (1088 bits)
    # pad: keccak padding 0x01 ... 0x80
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] ^= 0x80

    state = [0] * 25
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            lane = int.from_bytes(block[8 * i:8 * i + 8], "little")
            state[i] ^= lane
        state = _keccak_f(state)

    out = b"".join(state[i].to_bytes(8, "little") for i in range(25))
    return out[:32]


# ------------------------------------------------------------ VRF

def _be32(x: int) -> bytes:
    return x.to_bytes(32, "big")


def u_for(p: int, game_id: int, turn: int) -> int:
    dig = keccak256(b"flygammon-vrf-u" + _be32(game_id) + _be32(turn))
    u = int.from_bytes(dig, "big") % p
    if u < 2:
        u += 2
    return u


def dice_from_y(y: int):
    hh = int.from_bytes(keccak256(b"flygammon-vrf-dice" + _be32(y)), "big")
    d1 = (hh % 6) + 1
    d2 = ((hh >> 8) % 6) + 1
    return (d1, d2)


def dice_for_ply(p: int, s: int, game_id: int, turn: int):
    """The two dice for ply `turn` of game `game_id`, using the recovered secret."""
    u = u_for(p, game_id, turn)
    y = pow(u, s, p)
    return dice_from_y(y)
