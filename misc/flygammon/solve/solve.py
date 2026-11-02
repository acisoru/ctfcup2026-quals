#!/usr/bin/env python3
"""flygammon reference solver — the intended solution.

1. Read the public weak-VRF key (p, g, h) from the on-chain contract.
2. Recover the oracle secret s by Pohlig-Hellman (p-1 is smooth) => predict every
   future die of every game.
3. Use that foreknowledge (deterministic depth-2 search vs the fly's hedging
   2-ply play) to win games; preview each gameId and skip losing seeds; drive the
   streak to N and collect the flag.

Env / args:
  RPC_URL, CHALLENGE_ADDR, PLAYER_KEY   (required)
  MODEL_FLY (default ../../flygammon/artifacts/flygammon_best.fly), HIDDEN (80)
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import dlp
import engine as E
import net as NN
import vrf
from chain import Chain, arr

WIN = 1000.0
SHORTLIST = 6
DEPTH = 2
MAX_PLIES = 400


# ------------------------------------------------------------ foreknowledge search

def player_equity(model, b, mover_is_player):
    e = NN.equities(model, [b])[0]
    return e if mover_is_player else -e


def search(model, b, sched, ply, mover_is_player, depth):
    if E.current_won(b):
        pts = E.score_points(b)
        return WIN + pts if mover_is_player else -WIN - pts
    if ply >= len(sched):
        return player_equity(model, b, mover_is_player)
    dice = sched[ply]
    ends = E.legal_end_boards(b, dice)
    if not ends:
        return search(model, E.flip(b), sched, ply + 1, not mover_is_player, depth)

    if mover_is_player:
        oppeq = NN.equities(model, [E.flip(e) for e in ends])
        order = sorted(range(len(ends)), key=lambda i: oppeq[i])
        if depth <= 0:
            best = -1e30
            for i, e in enumerate(ends):
                v = WIN + E.score_points(e) if E.current_won(e) else -oppeq[i]
                best = max(best, v)
            return best
        best = -1e30
        for i in order[:SHORTLIST]:
            e = ends[i]
            if E.current_won(e):
                v = WIN + E.score_points(e)
            else:
                v = search(model, E.flip(e), sched, ply + 1, False, depth - 1)
            best = max(best, v)
        return best
    else:
        # Cheap 1-ply fly prediction inside the lookahead; we re-plan from the
        # real board each turn, so this approximation of the real 2-ply fly is fine.
        mv = NN.choose_1ply(model, b, dice)
        if mv is None:
            return search(model, E.flip(b), sched, ply + 1, True, depth)
        if E.current_won(mv):
            return -WIN - E.score_points(mv)
        return search(model, E.flip(mv), sched, ply + 1, True, depth)


def best_end(model, b, sched, ply, depth):
    dice = sched[ply]
    ends = E.legal_end_boards(b, dice)
    if not ends:
        return None
    for e in ends:
        if E.current_won(e):
            return e
    oppeq = NN.equities(model, [E.flip(e) for e in ends])
    order = sorted(range(len(ends)), key=lambda i: oppeq[i])
    best_i, best_v = order[0], -1e30
    for i in order[:SHORTLIST]:
        e = ends[i]
        if E.current_won(e):
            v = WIN + E.score_points(e)
        else:
            v = search(model, E.flip(e), sched, ply + 1, False, depth - 1)
        if v > best_v:
            best_v, best_i = v, i
    return ends[best_i]


def simulate_win(model, sched):
    """Would the player win this seed, with foreknowledge vs the 2-ply fly?"""
    b = E.new_game()
    player_turn = True
    ply = 0
    while ply < len(sched):
        dice = sched[ply]
        ends = E.legal_end_boards(b, dice)
        if not ends:
            b = E.flip(b)
            player_turn = not player_turn
            ply += 1
            continue
        if player_turn:
            chosen = best_end(model, b, sched, ply, DEPTH)
        else:
            chosen = NN.choose_2ply(model, b, dice)  # accurate model of the real fly
        if E.current_won(chosen):
            return player_turn
        b = E.flip(chosen)
        player_turn = not player_turn
        ply += 1
    return False


# ------------------------------------------------------------ driver

def schedule(p, s, game_id):
    return [vrf.dice_for_ply(p, s, game_id, t) for t in range(MAX_PLIES)]


def main():
    rpc = os.environ.get("RPC_URL", sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8545")
    addr = os.environ["CHALLENGE_ADDR"]
    pk = os.environ["PLAYER_KEY"]
    fly = os.environ.get("MODEL_FLY", os.path.join(os.path.dirname(__file__), "..", "..", "flygammon", "attempts", "h80_i100_distill", "flygammon_best.fly"))
    hidden = int(os.environ.get("HIDDEN", "80"))

    ch = Chain(rpc, addr, pk)

    p = ch.call_uint("P()(uint256)")
    g = ch.call_uint("G()(uint256)")
    h = ch.call_uint("H()(uint256)")
    n = ch.call_uint("N()(uint256)")
    print(f"[*] read public key: p~2^{p.bit_length()}, g={g}, N={n}")

    t0 = time.time()
    fac = dlp.factorize(p - 1)
    s = dlp.discrete_log(g, h, p, fac)
    assert pow(g, s, p) == h, "DLP failed"
    print(f"[+] recovered oracle secret s in {time.time()-t0:.2f}s  (factors: {sorted(fac)})")

    model = NN.FlyNet(fly, hidden)

    scheds = {}

    def sched_for(gid):
        if gid not in scheds:
            scheds[gid] = schedule(p, s, gid)
        return scheds[gid]

    while not ch.call_bool("isSolved()(bool)"):
        if not ch.call_bool("committed()(bool)"):
            gid = ch.call_uint("gameId()(uint256)")
            # Pre-commit preview: simulate the seed with foreknowledge and skip it if
            # unwinnable (skip is free, commit binds). This is the designed gating —
            # within one process the sim line == the played line, so a committed game
            # is a verified win. Disable with PREVIEW=0.
            if os.environ.get("PREVIEW", "1") == "1" and not simulate_win(model, sched_for(gid)):
                ch.send("skip()")
                print(f"[*] skipped unwinnable game {gid}")
                continue
            ch.send("commit()")
            print(f"[*] committed game {gid} (streak {ch.call_uint('streak()(uint256)')}, tokens {ch.call_uint('tokens()(uint256)')})")
            continue

        ptm = ch.call_bool("playerToMove()(bool)")
        dp = ch.call_bool("dicePosted()(bool)")
        if ptm and dp:
            gid = ch.call_uint("gameId()(uint256)")
            turn = ch.call_uint("turn()(uint256)")
            board = E.unpack_packed(ch.call_uint("boardPacked()(uint256)"))
            sched = sched_for(gid)
            end = best_end(model, board, sched, turn, DEPTH)
            if end is None:
                ch.send("playerMove(uint8[],uint8[])", "[]", "[]")
            else:
                path = E.path_to(board, sched[turn], end)
                froms = [m[0] for m in path]
                dies = [m[1] for m in path]
                ch.send("playerMove(uint8[],uint8[])", arr(froms), arr(dies))
                if E.current_won(end):
                    print(f"[+] won game {gid} -> streak {ch.call_uint('streak()(uint256)')}")
        else:
            time.sleep(0.1)  # wait for the daemon to post dice / play the fly

    print("[+] SOLVED — isSolved() == true")


if __name__ == "__main__":
    main()
