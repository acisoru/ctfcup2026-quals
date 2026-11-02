"""Backgammon engine — Python port of flygammon's engine.rs.

Board is canonical from the mover's perspective: positive = mover (moves 23->0,
bears off past 0, home = 0..5), negative = opponent (mirror). Used by the solver
to simulate games and to produce legal move PATHS the contract accepts.
"""

N = 24
CUR = 0
OPP = 1
BAR_FROM = 24


class Board:
    __slots__ = ("points", "bar", "off")

    def __init__(self, points=None, bar=None, off=None):
        self.points = points if points is not None else [0] * N
        self.bar = bar if bar is not None else [0, 0]
        self.off = off if off is not None else [0, 0]

    def clone(self):
        return Board(self.points[:], self.bar[:], self.off[:])

    def key(self):
        return (tuple(self.points), tuple(self.bar), tuple(self.off))

    def __eq__(self, o):
        return self.points == o.points and self.bar == o.bar and self.off == o.off


def new_game():
    p = [0] * N
    p[23] = 2
    p[12] = 5
    p[7] = 3
    p[5] = 5
    p[0] = -2
    p[11] = -5
    p[16] = -3
    p[18] = -5
    return Board(p, [0, 0], [0, 0])


def flip(b):
    p = [0] * N
    for i in range(N):
        p[i] = -b.points[N - 1 - i]
    return Board(p, [b.bar[OPP], b.bar[CUR]], [b.off[OPP], b.off[CUR]])


def all_current_home(b):
    if b.bar[CUR] > 0:
        return False
    return all(b.points[i] <= 0 for i in range(6, N))


def current_won(b):
    return b.off[CUR] == 15


def score_points(b):
    if b.off[OPP] > 0:
        return 1
    if any(b.points[i] < 0 for i in range(6)) or b.bar[OPP] > 0:
        return 3
    return 2


def single_moves_tagged(b, d):
    """List of (resulting Board, from) for one die d. from=24 means from bar."""
    res = []
    if b.bar[CUR] > 0:
        t = N - d
        if b.points[t] > -2:
            nb = b.clone()
            if nb.points[t] == -1:
                nb.points[t] = 0
                nb.bar[OPP] += 1
            nb.points[t] += 1
            nb.bar[CUR] -= 1
            res.append((nb, BAR_FROM))
        return res

    home = all_current_home(b)
    for p in range(N):
        if b.points[p] <= 0:
            continue
        target = p - d
        if target >= 0:
            t = target
            if b.points[t] > -2:
                nb = b.clone()
                if nb.points[t] == -1:
                    nb.points[t] = 0
                    nb.bar[OPP] += 1
                nb.points[t] += 1
                nb.points[p] -= 1
                res.append((nb, p))
        elif home:
            pip = p + 1
            if d == pip:
                nb = b.clone()
                nb.points[p] -= 1
                nb.off[CUR] += 1
                res.append((nb, p))
            elif d > pip:
                if not any(b.points[i] > 0 for i in range(p + 1, 6)):
                    nb = b.clone()
                    nb.points[p] -= 1
                    nb.off[CUR] += 1
                    res.append((nb, p))
    return res


def _dfs(board, dice, path, out):
    advanced = False
    for i in range(len(dice)):
        d = dice[i]
        rest = dice[:i] + dice[i + 1:]
        for nb, frm in single_moves_tagged(board, d):
            advanced = True
            path.append((frm, d))
            _dfs(nb, rest, path, out)
            path.pop()
    if not advanced:
        out.append((board.clone(), path[:]))


def legal_end_boards_with_paths(board, dice):
    """List of (end Board, path) for the roll (d1, d2). Path is max-length, with
    the larger-die rule applied; de-duplicated by end position."""
    if dice[0] == dice[1]:
        multiset = [dice[0]] * 4
    else:
        multiset = [dice[0], dice[1]]

    leaves = []
    _dfs(board, multiset, [], leaves)
    if not leaves:
        return []
    max_len = max(len(p) for _, p in leaves)
    if max_len == 0:
        return []
    kept = [(b, p) for (b, p) in leaves if len(p) == max_len]

    if max_len == 1 and dice[0] != dice[1]:
        larger = max(dice[0], dice[1])
        if any(p[0][1] == larger for _, p in kept):
            kept = [(b, p) for (b, p) in kept if p[0][1] == larger]

    out = []
    seen = set()
    for b, p in kept:
        k = b.key()
        if k not in seen:
            seen.add(k)
            out.append((b, p))
    return out


def legal_end_boards(board, dice):
    return [b for b, _ in legal_end_boards_with_paths(board, dice)]


def unpack_packed(key):
    """Decode the Solidity-packed board key (points 6-bit two's complement at
    6*i; bar/off 5-bit at offset 144) into a Board."""
    points = [0] * N
    for i in range(N):
        v = (key >> (6 * i)) & 0x3f
        points[i] = v - 64 if v >= 32 else v
    base = 144
    bar = [(key >> base) & 0x1f, (key >> (base + 5)) & 0x1f]
    off = [(key >> (base + 10)) & 0x1f, (key >> (base + 15)) & 0x1f]
    return Board(points, bar, off)


def path_to(board, dice, target):
    for b, p in legal_end_boards_with_paths(board, dice):
        if b == target:
            return p
    return None
