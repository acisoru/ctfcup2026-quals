from concurrent.futures import ProcessPoolExecutor

from z3 import BitVec, Concat, Or, RotateLeft, Solver, ZeroExt, sat

M = 0xFFFFFFFF
PREFIX = b"ctfcup{"
CHARSET = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
LENGTH = 67
TARGETS = (
    (0xC49415C3, 0x9B98BC82),
    (0xEE721BB8, 0x405755CC),
    (0xC347A011, 0xC00165C9),
    (0x7660B2CC, 0x5C7BD094),
    (0x4FCB8CCE, 0xE8703417),
    (0x922A5F7B, 0x8B0C584A),
    (0x8CB6990F, 0x18AF8FB5),
    (0x8C66A050, 0x7EC28CC3),
    (0x277F03E5, 0x089CBD6B),
)
ROUTE_TARGET = 0x50BDE111
GLOBAL_TARGET = (0x6772A166, 0x9C35B18C)
KEY_SEED, KEY_XOR, KEY_ADD = 3235782708, 2779108127, 2654435769
SALT_SEED, SALT_ADD, SALT_XOR = 1779017063, 2135587861, 2246822507
MASK_SEED, MASK_XOR, MASK_ADD = 3139743365, 3518319157, 3266489917


def rol(value, count):
    if isinstance(value, int):
        return ((value << count) | (value >> (32 - count))) & M
    return RotateLeft(value, count)


def schedule():
    key, salt, mask = KEY_SEED, SALT_SEED, MASK_SEED
    result = []
    for _ in TARGETS:
        key = (rol(key ^ KEY_XOR, 9) + KEY_ADD) & M
        salt = rol((salt + SALT_ADD) & M, 13) ^ SALT_XOR
        mask = (rol(mask ^ MASK_XOR, 17) + MASK_ADD) & M
        result.append((key, salt, mask))
    return result


def expand(data, state):
    key, salt, mask = state
    lanes = [[], [], [], []]
    for i, byte in enumerate(data):
        a = ~byte ^ ((key >> (8 * (i & 3))) & 255)
        b = byte + ((salt >> (8 * ((i + 1) & 3))) & 255)
        c = a ^ b ^ ((mask >> (8 * ((i + 2) & 3))) & 255)
        d = c + byte
        for lane, value in zip(lanes, (a, b, c, d)):
            lane.append(value & 255 if isinstance(value, int) else value)
    return lanes


def pack4(values):
    if isinstance(values[0], int):
        return sum(value << (8 * i) for i, value in enumerate(values))
    return Concat(*reversed(values))


def seed(index):
    return (0x9E3779B9 ^ (((index + 1) * 0x13579BDF) & M),
            0x85EBCA6B ^ (((index + 1) * 0x27D4EB2D) & M))


def word(byte):
    return byte if isinstance(byte, int) else ZeroExt(24, byte)


def hash_a(lanes, index):
    left, right = seed(index)
    for j in range(8):
        lane = word(lanes[0][j]) + 0x101 + j * 0x41
        left = rol(((left ^ lane) + right) & M, 5 + j % 7)
        right = rol((right + (lane ^ left)) & M, 11 + j % 5) ^ left
    return left, right


def hash_b(lanes, index):
    left, right = seed(index)
    for j in range(6):
        lane = word(lanes[0][j]) + 0x101 + j * 0x41
        right = rol(((right ^ lane) + left) & M, 7 + j % 9)
        left = rol((left + (lane ^ right)) & M, 11 + j % 7) ^ right
    return left ^ pack4(lanes[3][4:]), right ^ pack4(lanes[2][:4])


def hash_c(lanes, index):
    left, right = seed(index)
    for j in range(4):
        lane = word(lanes[j & 1][j]) + 0x101 + j * 0x41
        left = rol((left ^ (lane + right)) & M, 5 + j % 7)
    for j in range(4, 8):
        lane = word(lanes[j & 1][j]) + 0x101 + j * 0x41
        right = rol((right + lane) & M, 13 + j % 7) ^ left
    return left ^ pack4(lanes[3][4:]), right ^ pack4(lanes[2][:4])


def hash_d(lanes, index):
    left, right = seed(index)
    for j in range(4):
        lane = word(lanes[1 - (j & 1)][j]) + 0x101 + j * 0x41
        left = rol((left + lane) & M, 9 + j % 7) ^ (lane ^ right)
    for j in range(4, 8):
        lane = word(lanes[1 - (j & 1)][j]) + 0x101 + j * 0x41
        right = (rol((right ^ lane) & M, 11 + j % 5) + (lane ^ left)) & M
    return left ^ pack4(lanes[3][4:]), right ^ pack4(lanes[2][:4])


HASHES = (hash_a, hash_b, hash_c, hash_d)


def solve_chunk(index):
    values = [BitVec(f"b{index}_{j}", 8) for j in range(8)]
    solver = Solver()
    solver.set(timeout=420000)
    for j, value in enumerate(values):
        position = index * 8 + j
        if position < len(PREFIX):
            solver.add(value == PREFIX[position])
        elif position == LENGTH - 1:
            solver.add(value == ord("}"))
        elif position >= LENGTH:
            solver.add(value == 0)
        else:
            solver.add(Or(*(value == ch for ch in CHARSET)))
    result = HASHES[index % 4](expand(values, schedule()[index]), index)
    solver.add(result[0] == TARGETS[index][0], result[1] == TARGETS[index][1])
    status = solver.check()
    if status != sat:
        raise RuntimeError(f"chunk {index}: {status}, {solver.reason_unknown()}")
    model = solver.model()
    return bytes(model.eval(value).as_long() for value in values)


def validate(candidate):
    padded = candidate + bytes(len(TARGETS) * 8 - len(candidate))
    blocks = [expand(padded[i * 8:(i + 1) * 8], state)
              for i, state in enumerate(schedule())]
    if any(HASHES[i % 4](lanes, i) != target
           for i, (lanes, target) in enumerate(zip(blocks, TARGETS))):
        return False
    route = 0x5A17D1E3
    for i, (left, right) in enumerate(TARGETS):
        mixed = left ^ rol(right, 13) ^ (((i + 1) * 0x9E3779B9) & M)
        route = (rol(route ^ mixed, 7 + i % 11) + 0x7F4A7C15) & M
    if route != ROUTE_TARGET:
        return False
    left, right = 0x243F6A88, 0x85A308D3
    for i, lanes in enumerate(blocks):
        for lane_no, values in enumerate(lanes):
            low, high = pack4(values[:4]), pack4(values[4:])
            left = rol(((left ^ low) + right) & M, 7 + (i + lane_no) % 9)
            right = (rol(((right + high) & M) ^ left,
                         11 + (i + lane_no) % 7) + low) & M
    return (left, right) == GLOBAL_TARGET


if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=4) as pool:
        chunks = list(pool.map(solve_chunk, range(len(TARGETS))))
    candidate = b"".join(chunks)[:LENGTH]
    if not validate(candidate):
        raise RuntimeError("global check failed")
    print(candidate.decode())
