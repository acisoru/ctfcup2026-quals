#!/usr/bin/env python3
"""
Reference solver for "khudozhestvenniy film" (Lucky Spire casino).

Uses ONLY public chain data (eth_get*, logs, traces) that a player would have.
Reconstructs the hack from scratch:

  1. Find the casino + its fulfillRandomness callers (the "oracles"). Group fulfillers.
  2. Spot the rogue oracle: a fulfiller that is NOT one of the sanctioned (rotateOracle'd)
     addresses, yet settled winning bets.
  3. Confirm the oracle slot changed WITHOUT a rotateOracle call -> something wrote slot 2
     via the delegatecalled engine.
  4. Show the engine address H has DIFFERENT codehash across history (metamorphic).
  5. Identify the insider: the operator that performed the engine re-mints (destroyHub/spawnHub
     + deployGame-onto-H) aligned with the rogue-oracle windows.
  6. Identify drainers: accounts whose winning bets were fulfilled by the rogue oracle.

Run against the generated anvil node (or the shipped archive node).
"""
import subprocess, json, os, sys
from collections import defaultdict

RPC = os.environ.get("RPC", "http://127.0.0.1:8545")

def sh(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(a)}\n{r.stderr}")
    return r.stdout.strip()

def clean(s): return s.split()[0] if s else s
def rpc(method, *params):
    args = ["cast", "rpc", "--rpc-url", RPC, method] + list(params)
    return sh(*args)
def call(to, sig, *args): return clean(sh("cast", "call", "--rpc-url", RPC, to, sig, *map(str, args)))
def code_at(addr, block=None):
    a = ["cast", "code", addr, "--rpc-url", RPC]
    if block is not None: a += ["--block", str(block)]
    return sh(*a)
def keccak(h): return sh("cast", "keccak", h)
def latest_block(): return int(clean(sh("cast", "block-number", "--rpc-url", RPC)))

# event topics
TOPIC_SETTLED = keccak('0x' + 'BetSettled(uint256,bool,uint256)'.encode().hex())  # not used directly; use signature
def topic(sig): return keccak('0x' + sig.encode().hex())

def get_logs(address=None, topics=None, from_block=0, to_block="latest"):
    import json as _j
    params = {"fromBlock": hex(from_block) if isinstance(from_block,int) else from_block,
              "toBlock": to_block if isinstance(to_block,str) else hex(to_block)}
    if address: params["address"] = address
    if topics: params["topics"] = topics
    out = rpc("eth_getLogs", _j.dumps(params))
    return _j.loads(out)

def main(casino):
    print(f"[*] casino = {casino}")
    latest = latest_block()
    print(f"[*] latest block = {latest}")

    # guard: the 411M archive takes ~20s to ingest; anvil answers at block 0 before it's loaded.
    if latest == 0 or len(code_at(casino)) <= 2:
        print("\n[!] node looks empty (block 0 / no casino code).")
        print("    The archive is still loading — anvil accepts requests before it finishes")
        print("    ingesting the 411M state. Wait until `cast block-number` reports a non-zero")
        print("    block (~20s), then re-run. See public/readme.md.")
        sys.exit(1)

    # --- engine address (public getter) and its CURRENT codehash
    engine = call(casino, "getEngine()(address)")
    cur_code = code_at(engine)
    print(f"[*] engine H = {engine}  current codehash = {keccak(cur_code)}")

    # --- scan all BetSettled + who sent the fulfill tx for each settled bet
    t_settled = topic("BetSettled(uint256,bool,uint256)")
    t_rotate  = topic("OracleRotated(address)")
    t_placed  = topic("BetPlaced(uint256,address,uint8,uint256,uint256)")

    settled = get_logs(casino, [t_settled], 0, latest)
    print(f"[*] {len(settled)} BetSettled events")

    # map each settle to the tx sender (the fulfiller / "oracle")
    fulfiller_of_bet = {}
    won_of_bet = {}
    fulfiller_counts = defaultdict(int)
    fulfiller_wins = defaultdict(int)
    for lg in settled:
        betId = int(lg["topics"][1], 16)
        data = lg["data"][2:]
        won = int(data[0:64], 16) == 1
        txh = lg["transactionHash"]
        tx = json.loads(rpc("eth_getTransactionByHash", txh))
        sender = tx["from"]
        fulfiller_of_bet[betId] = sender
        won_of_bet[betId] = won
        fulfiller_counts[sender] += 1
        if won: fulfiller_wins[sender] += 1

    print("\n[*] fulfillers (settle tx senders):")
    for f, n in sorted(fulfiller_counts.items(), key=lambda x:-x[1]):
        print(f"      {f}  settled={n} wins={fulfiller_wins[f]}")

    # --- sanctioned oracles = addresses set via OracleRotated + the constructor oracle.
    # The ctor oracle is the fulfiller active in the EARLIEST settle (before any rotate).
    rotated = get_logs(casino, [t_rotate], 0, latest)
    rotated_sorted = sorted(rotated, key=lambda l: (int(l["blockNumber"],16), int(l["logIndex"],16)))
    sanctioned = set()
    rotate_blocks = []
    for lg in rotated_sorted:
        a = "0x" + lg["topics"][1][-40:]
        sanctioned.add(a.lower())
        rotate_blocks.append((int(lg["blockNumber"],16), a.lower()))
    # constructor oracle: fulfiller of the lowest-block settle
    first_settle = min(settled, key=lambda l:(int(l["blockNumber"],16), int(l["logIndex"],16)))
    fb_tx = json.loads(rpc("eth_getTransactionByHash", first_settle["transactionHash"]))
    ctor_oracle = fb_tx["from"].lower()
    sanctioned.add(ctor_oracle)
    print(f"\n[*] constructor oracle (earliest fulfiller): {ctor_oracle}")
    print(f"[*] sanctioned oracles (ctor + rotateOracle): {sanctioned}")

    # rogue = a fulfiller never sanctioned
    rogue = [f for f in fulfiller_counts if f.lower() not in sanctioned]
    # the deployer/owner may have set the initial oracle in ctor (not a rotate) -> allow it if it only
    # fulfilled early; the true rogue is the one with wins and not sanctioned and not the ctor oracle.
    print(f"[*] candidate rogue fulfillers (not rotated-in): {rogue}")

    # --- drainers vs cover-noise players ---
    # The rogue oracle fulfils TWO kinds of bets during its windows:
    #   * drainers: the attacker grinds a winning word every time -> they NEVER lose to the rogue;
    #   * cover-noise: ordinary players whose bets the rogue fulfils with honest random words
    #     -> they win some and lose some (normal win rate).
    # So a drainer = an address fulfilled by the rogue that won EVERY one of its rogue-fulfilled
    # bets (and bet more than once). Ordinary players have mixed results under the rogue.
    # BetPlaced(betId indexed, player indexed, game, amount, requestId): amount is data word 1.
    rogue_set = {r.lower() for r in rogue}
    placed = get_logs(casino, [t_placed], 0, latest)
    bet_player = {}
    bet_amount = {}
    for lg in placed:
        betId = int(lg["topics"][1], 16)
        bet_player[betId] = ("0x" + lg["topics"][2][-40:]).lower()
        data = lg["data"][2:]
        bet_amount[betId] = int(data[64:128], 16)   # 2nd non-indexed word = amount

    rogue_wins = defaultdict(int)
    rogue_losses = defaultdict(int)
    rogue_won_wei = defaultdict(int)
    for betId, f in fulfiller_of_bet.items():
        if f.lower() in rogue_set and betId in bet_player:
            p = bet_player[betId]
            if won_of_bet[betId]:
                rogue_wins[p] += 1
                rogue_won_wei[p] += bet_amount.get(betId, 0)
            else:
                rogue_losses[p] += 1

    # A drainer: never loses to the rogue, bets >=2 times, AND stakes large sums (the attacker
    # grinds wins on big bets to actually drain the bankroll). Cover-noise players that got lucky
    # bet tiny amounts, so a stake threshold cleanly separates them.
    BIG = 100 * 10**18   # drainers stake hundreds of ETH; noise is 1-40 ETH
    drainer_addrs = {p: rogue_wins[p] for p in rogue_wins
                     if rogue_losses[p] == 0 and rogue_wins[p] >= 2 and rogue_won_wei[p] >= BIG}

    print(f"\n[*] addresses the rogue fulfilled (win/loss / total won under rogue):")
    for p in sorted(set(rogue_wins) | set(rogue_losses), key=lambda x: -rogue_won_wei[x]):
        tag = " <- DRAINER" if p in drainer_addrs else " (cover noise)"
        print(f"      {p}  w={rogue_wins[p]} l={rogue_losses[p]} won={rogue_won_wei[p]//10**18}eth{tag}")
    print(f"\n[*] DRAINERS (never lose to rogue + large stakes): {len(drainer_addrs)}")
    for a, n in sorted(drainer_addrs.items(), key=lambda x:-x[1]):
        print(f"      {a}  rogue-wins={n}  won={rogue_won_wei[a]//10**18}eth")

    # --- metamorphic proof: engine H codehash changed across history ---
    # sample codehash at H around each window vs baseline. Use hub GameDeployed logs where the
    # deployed address == engine (H): those are the re-mints.
    t_gamedep = topic("GameDeployed(address,uint256)")
    hub = call(casino, "getHub()(address)")
    gd = get_logs(hub, [t_gamedep], 0, latest)
    remints = []
    for lg in gd:
        dep_addr = "0x" + lg["data"][2:][24:64]
        if dep_addr.lower() == engine.lower():
            blk = int(lg["blockNumber"], 16)
            txh = lg["transactionHash"]
            tx = json.loads(rpc("eth_getTransactionByHash", txh))
            ch = keccak(code_at(engine, blk))
            remints.append((blk, tx["from"].lower(), ch))
    print(f"\n[*] engine re-mints onto H (metamorphic swaps), {len(remints)} total:")
    distinct_hashes = set()
    for blk, who, ch in remints:
        distinct_hashes.add(ch)
        print(f"      block {blk} by {who}  codehash {ch[:18]}..")
    print(f"[*] distinct codehashes ever at H: {len(distinct_hashes)} (>1 proves metamorphic)")

    # insider = the sender of re-mints that installed the RIGGED code.
    # honest codehash = what H held at genesis (right after buildEngine, long before any window).
    # Find the block H first got code by scanning early blocks.
    EMPTY = keccak("0x")
    honest_hash = None
    for b in range(1, 60):
        h = keccak(code_at(engine, b))
        if h != EMPTY:
            honest_hash = h
            break
    insiders = set()
    for blk, who, ch in remints:
        if ch != honest_hash:
            insiders.add(who)
    print(f"\n[*] honest engine codehash: {honest_hash[:18] if honest_hash else None}..")
    print(f"[*] INSIDER(s) who installed rigged engine: {insiders}")

    print(f"\n[*] ROGUE ORACLE: {rogue}")
    return {"engine": engine, "rogue": rogue, "drainers": list(drainer_addrs),
            "insiders": list(insiders), "remints": len(remints),
            "distinct_hashes": len(distinct_hashes)}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        casino = sys.argv[1]
    else:
        # default: read the generator's answer key (sibling deploy/ dir)
        here = os.path.dirname(os.path.abspath(__file__))
        ans = os.path.join(here, "..", "deploy", "answer.json")
        casino = json.load(open(ans))["casino"]
    main(casino)
