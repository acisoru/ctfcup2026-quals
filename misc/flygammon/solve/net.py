"""FlyNet inference in numpy — ports features.rs, model.rs, agent.rs.

Loads the raw little-endian f32 `.fly` artifact: for each of 3 Linear layers,
weight [in, out] row-major then bias [out]. Forward: relu(l1) -> relu(l2) ->
sigmoid(l3), 5 outputs; equity = 2*r0-1 + r1 + r2 - r3 - r4.
"""

import numpy as np

import engine as E

N_INPUT = 24 * 8 + 4 + 7  # 203
N_OUTPUT = 5


class FlyNet:
    def __init__(self, path, hidden=80):
        raw = np.fromfile(path, dtype="<f4")
        sizes = [
            (N_INPUT, hidden),
            (hidden, hidden),
            (hidden, N_OUTPUT),
        ]
        off = 0
        self.W = []
        self.b = []
        for (din, dout) in sizes:
            w = raw[off:off + din * dout].reshape(din, dout)
            off += din * dout
            bias = raw[off:off + dout]
            off += dout
            self.W.append(w)
            self.b.append(bias)
        assert off == raw.size, f"weight size mismatch: used {off} of {raw.size}"

    def forward(self, X):
        x = np.maximum(X @ self.W[0] + self.b[0], 0.0)
        x = np.maximum(x @ self.W[1] + self.b[1], 0.0)
        z = x @ self.W[2] + self.b[2]
        return 1.0 / (1.0 + np.exp(-z))


def _unary(v, base, n):
    v[base] = 1.0
    if n >= 2:
        v[base + 1] = 1.0
    if n >= 3:
        v[base + 2] = 1.0
    if n > 3:
        v[base + 3] = (n - 3.0) / 2.0


def encode(b):
    v = np.zeros(N_INPUT, dtype="<f4")
    for i in range(E.N):
        c = b.points[i]
        base = i * 8
        if c > 0:
            _unary(v, base, c)
        elif c < 0:
            _unary(v, base + 4, -c)
    g = E.N * 8  # 192
    v[g] = b.bar[E.CUR] / 2.0
    v[g + 1] = b.bar[E.OPP] / 2.0
    v[g + 2] = b.off[E.CUR] / 15.0
    v[g + 3] = b.off[E.OPP] / 15.0

    pip_own = b.bar[E.CUR] * 25
    pip_opp = b.bar[E.OPP] * 25
    home_own = home_opp = blots_own = blots_opp = 0
    for i in range(E.N):
        c = b.points[i]
        if c > 0:
            pip_own += c * (i + 1)
            if i < 6 and c >= 2:
                home_own += 1
            if c == 1:
                blots_own += 1
        elif c < 0:
            pip_opp += (-c) * (E.N - i)
            if i >= 18 and c <= -2:
                home_opp += 1
            if c == -1:
                blots_opp += 1
    e = g + 4  # 196
    v[e] = pip_own / 167.0
    v[e + 1] = pip_opp / 167.0
    v[e + 2] = (pip_opp - pip_own) / 167.0
    v[e + 3] = home_own / 6.0
    v[e + 4] = home_opp / 6.0
    v[e + 5] = blots_own / 15.0
    v[e + 6] = blots_opp / 15.0
    return v


def equity_from_row(r):
    return 2.0 * r[0] - 1.0 + r[1] + r[2] - r[3] - r[4]


def equities(net, boards):
    if not boards:
        return []
    X = np.stack([encode(b) for b in boards]).astype("<f4")
    out = net.forward(X)
    return [equity_from_row(out[i]) for i in range(out.shape[0])]


def dice_combos():
    v = []
    for a in range(1, 7):
        for b in range(a, 7):
            w = 1.0 / 36.0 if a == b else 2.0 / 36.0
            v.append(((a, b), w))
    return v


def choose_1ply(net, board, dice):
    ends = E.legal_end_boards(board, dice)
    if not ends:
        return None
    for e in ends:
        if E.current_won(e):
            return e
    opp = equities(net, [E.flip(e) for e in ends])
    best = min(range(len(ends)), key=lambda i: opp[i])
    return ends[best]


TWO_PLY_CANDIDATES = 8


def choose_2ply(net, board, dice):
    ends = E.legal_end_boards(board, dice)
    if not ends:
        return None
    for e in ends:
        if E.current_won(e):
            return e

    opp1 = equities(net, [E.flip(e) for e in ends])
    order = sorted(range(len(ends)), key=lambda i: opp1[i])
    k = min(TWO_PLY_CANDIDATES, len(ends))
    shortlist = order[:k]

    combos = dice_combos()
    # Build ONE batch over all shortlisted candidates, all 21 opponent rolls and
    # all opponent replies (plus each candidate's "opponent passes" position).
    boards = []
    cands = []  # (ei, base_idx, [(w, start, end)])
    for ei in shortlist:
        e = ends[ei]
        base_idx = len(boards)
        boards.append(e)
        e_opp = E.flip(e)
        spans = []
        for d, w in combos:
            opp_ends = E.legal_end_boards(e_opp, d)
            start = len(boards)
            for oe in opp_ends:
                boards.append(E.flip(oe))
            spans.append((w, start, len(boards)))
        cands.append((ei, base_idx, spans))

    eqs = equities(net, boards)
    best_i, best_val = shortlist[0], -1e30
    for ei, base_idx, spans in cands:
        base = eqs[base_idx]
        val = 0.0
        for w, start, end in spans:
            vd = base if start == end else min(eqs[start:end])
            val += w * vd
        if val > best_val:
            best_val, best_i = val, ei
    return ends[best_i]
