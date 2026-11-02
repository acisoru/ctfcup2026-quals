#!/usr/bin/env bash
# Run AFTER generate.py completes (anvil still running on :8545).
# Cleanly stops anvil, waits for the state dump to FULLY flush (size stable),
# keeps the raw .json, makes a .gz, then verifies the handout reloads + solves.
set -uo pipefail
cd "$(dirname "$0")/.."     # task root
RPC=http://127.0.0.1:8545
STATE=public/luckyspire.state.json

echo "[1] stopping anvil (SIGINT triggers the state dump)"
pkill -INT -f "port 8545" 2>/dev/null || true

echo "[2] waiting for dump to flush (size must stabilize)"
prev=-1
for i in $(seq 1 90); do
  sleep 2
  sz=$(stat -f%z "$STATE" 2>/dev/null || echo 0)
  echo "    dump size: $sz"
  if [ "$sz" != "0" ] && [ "$sz" = "$prev" ]; then echo "    -> stable"; break; fi
  prev=$sz
done
pkill -f "port 8545" 2>/dev/null || true
sleep 1

echo "[3] validate dump is complete JSON"
python3 -c "import json;json.load(open('$STATE'));print('    VALID JSON')" || { echo "    DUMP INVALID — abort"; exit 1; }
ls -lah "$STATE"

echo "[4] build handout tar.gz (chain only; keep raw state for local testing)"
( cd public && tar -czf luckyspire-chain.tar.gz luckyspire.state.json )
ls -lah public/luckyspire-chain.tar.gz

echo "[5] verify: reload RAW + historical query"
pkill -f anvil 2>/dev/null || true; sleep 1
nohup anvil --hardfork shanghai --preserve-historical-states --state "$STATE" --port 8545 >/tmp/verify-anvil.log 2>&1 &
for i in $(seq 1 40); do cast block-number --rpc-url $RPC >/dev/null 2>&1 && break; sleep 2; done
echo "    block: $(cast block-number --rpc-url $RPC 2>&1)"
H=$(python3 -c "import json;print(json.load(open('deploy/answer.json'))['engine_H'])")
echo "    engine H: $H"
echo "    hist code @ H block 300 (in a window): $(cast code $H --rpc-url $RPC --block 300 2>&1 | head -c 24)"
echo "    code @ H latest (honest, post-coverup): $(cast code $H --rpc-url $RPC 2>&1 | head -c 24)"

echo "[6] run reference solver against the reloaded handout"
python3 solve/solve.py 2>&1 | grep -E "fulfillers|settled=|ROGUE|INSIDER|DRAINERS|wins=|distinct codehashes|honest engine|re-mints onto"

pkill -f anvil 2>/dev/null || true
echo "[done] handout: $STATE (raw) + ${STATE}.gz"
