#!/usr/bin/env bash
# Per-instance bootstrap: fresh VRF params + random oracle/player keys, anvil,
# deploy, daemon, and a single front-door proxy (RPC + info + flag).
set -euo pipefail

INTERNAL=http://127.0.0.1:8546            # anvil, never exposed directly
WIN_N=${WIN_N:-15}
COMMIT_BUDGET=${COMMIT_BUDGET:-60}
FACTOR_BITS=${FACTOR_BITS:-40}
FLAG=${FLAG:-flag{replace_me}}
# anvil default account 0 — used only to fund fresh keys and deploy (no on-chain powers).
DEPLOYER_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

# No proxying for localhost RPC traffic (a stray *_PROXY env can stall 127.0.0.1).
export NO_PROXY='*' no_proxy='*'
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy || true

echo "[instance] starting anvil"
# --prune-history bounds anvil's memory on long streaks (old states are dropped;
# nothing in the game reads historical state)
anvil --port 8546 --gas-limit 300000000000 --base-fee 0 --quiet --prune-history 2>&1 | sed 's/^/[anvil] /' &
until cast block-number --rpc-url "$INTERNAL" >/dev/null 2>&1; do sleep 0.3; done

echo "[instance] minting keys"
PLAYER_KEY=0x$(openssl rand -hex 32)
PLAYER_ADDR=$(cast wallet address "$PLAYER_KEY")
ORACLE_KEY=0x$(openssl rand -hex 32)
ORACLE_ADDR=$(cast wallet address "$ORACLE_KEY")
cast send "$PLAYER_ADDR" --value 100ether --private-key "$DEPLOYER_KEY" --rpc-url "$INTERNAL" >/dev/null
cast send "$ORACLE_ADDR" --value 100ether --private-key "$DEPLOYER_KEY" --rpc-url "$INTERNAL" >/dev/null

echo "[instance] generating VRF params"
cd /app/tools
eval "$(python3 make_instance_params.py "$FACTOR_BITS")"   # sets PARAM_P/G/H, ORACLE_S

echo "[instance] deploying league contract"
cd /app/project
ADDR=$(forge create src/Flygammon.sol:Flygammon --rpc-url "$INTERNAL" \
    --private-key "$DEPLOYER_KEY" --broadcast --constructor-args \
    "$PARAM_P" "$PARAM_G" "$PARAM_H" "$PLAYER_ADDR" "$ORACLE_ADDR" "$WIN_N" "$COMMIT_BUDGET" \
    | grep 'Deployed to:' | awk '{print $3}')
echo "[instance] challenge at $ADDR"

echo "[instance] starting fly daemon"
# Diagnostics: make daemon startup failures visible in the instance logs (on the
# platform the daemon previously died silently — nothing from it ever appeared).
if [ -x /app/flygammon-daemon ]; then
  echo "[instance] fly daemon binary ok: $(ls -la /app/flygammon-daemon)"
else
  echo "[instance] ERROR: /app/flygammon-daemon missing or not executable:" >&2
  ls -la /app >&2 || true
fi
# Supervised launch: if the daemon dies (panic, exec format error, OOM kill, ...)
# the failure is logged with its exit code and the daemon is restarted, so one
# crash no longer leaves the instance permanently frozen mid-game.
(
  # errexit would kill this supervisor on the very first daemon crash — the
  # whole point here is to observe the exit and restart.
  set +e
  while true; do
    echo "[instance] fly daemon: launching"
    RPC_URL="$INTERNAL" ORACLE_KEY="$ORACLE_KEY" CHALLENGE_ADDR="$ADDR" \
      PARAM_P="$PARAM_P" PARAM_G="$PARAM_G" PARAM_H="$PARAM_H" ORACLE_S="$ORACLE_S" \
      MODEL_STEM=/app/flygammon_best HIDDEN=80 RUST_BACKTRACE=1 \
      /app/flygammon-daemon
    rc=$?
    case "$rc" in
      0)   why="" ;;
      126) why=" (exec failed — bad binary/arch/permissions)" ;;
      127) why=" (binary not found)" ;;
      134) why=" (SIGABRT — panic/abort, see backtrace above)" ;;
      137) why=" (SIGKILL — almost certainly OOM-killed: raise memoryLimit)" ;;
      139) why=" (SIGSEGV)" ;;
      *)   why="" ;;
    esac
    echo "[instance] fly daemon EXITED rc=$rc$why — restarting in 2s" >&2
    sleep 2
  done
) &

sleep 0.5

echo "[instance] starting front-door on :8545 (RPC + info + flag)"
exec env CHALLENGE_ADDR="$ADDR" PLAYER_KEY="$PLAYER_KEY" FLAG="$FLAG" WIN_N="$WIN_N" \
  /app/flygammon-proxy 8545 "$INTERNAL"
