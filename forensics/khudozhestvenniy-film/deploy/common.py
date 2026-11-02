#!/usr/bin/env python3
"""Shared harness for the Lucky Spire chain generator. Drives anvil via `cast`."""
import subprocess, json, os, sys

RPC = os.environ.get("RPC", "http://127.0.0.1:8545")
# deterministic mnemonic (anvil default) -> we derive many accounts by index
MNEMONIC = "test test test test test test test test test test test junk"

def sh(*args, check=True):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(args)}\n{r.stderr}\n{r.stdout}")
    return r.stdout.strip()

def clean_num(s):
    # cast pretty-prints big ints with a trailing " [1.2e77]" — strip it
    return s.split()[0] if s else s

# ---- account derivation (index -> (addr, privkey)) ----
_acct_cache = {}
def acct(i):
    if i in _acct_cache: return _acct_cache[i]
    pk = sh("cast", "wallet", "private-key", "--mnemonic", MNEMONIC, "--mnemonic-index", str(i))
    addr = sh("cast", "wallet", "address", "--private-key", pk)
    _acct_cache[i] = (addr, pk)
    return _acct_cache[i]

# ---- rpc helpers ----
def rpc(method, *params):
    args = ["cast", "rpc", "--rpc-url", RPC, method] + [json.dumps(p) if not isinstance(p, str) else p for p in params]
    return sh(*args)

def set_next_timestamp(ts):
    rpc("evm_setNextBlockTimestamp", str(ts))

def mine():
    rpc("evm_mine")

def set_balance(addr, wei):
    rpc("anvil_setBalance", addr, hex(wei))

def send(pk, to, sig, *args, value=None):
    cmd = ["cast", "send", "--private-key", pk, "--rpc-url", RPC, to, sig, *map(str, args)]
    if value is not None:
        cmd += ["--value", str(value)]
    cmd += ["--json"]
    out = sh(*cmd)
    return json.loads(out)

def create(pk, initcode, value=None):
    cmd = ["cast", "send", "--private-key", pk, "--rpc-url", RPC, "--create", initcode]
    if value is not None: cmd += ["--value", str(value)]
    cmd += ["--json"]
    out = sh(*cmd)
    return json.loads(out)["contractAddress"]

def call(to, sig, *args):
    out = sh("cast", "call", "--rpc-url", RPC, to, sig, *map(str, args))
    return clean_num(out)

def code(addr):
    return sh("cast", "code", addr, "--rpc-url", RPC)

def codelen(addr):
    c = code(addr)
    return (len(c) - 2) // 2

def keccak(hexdata):
    return sh("cast", "keccak", hexdata)

def abi_encode(sig, *args):
    return sh("cast", "abi-encode", sig, *map(str, args))

def compute_create(deployer, nonce):
    return sh("cast", "compute-address", deployer, "--nonce", str(nonce), "--rpc-url", RPC).split()[-1]

def nonce(addr):
    return int(clean_num(sh("cast", "nonce", addr, "--rpc-url", RPC)))

# roll = uint256(keccak256(abi.encode(word, clientSeed))) % 10000  (matches Casino._evaluate input)
def roll_for(word, client_seed):
    enc = abi_encode("f(uint256,bytes32)", word, client_seed)
    h = keccak(enc)
    return int(h, 16) % 10000

# win thresholds (out of 10000) from Casino._evaluate
THRESH = {0: 490, 1: 4900, 2: 4900}

def find_winning_word(game, client_seed, start=0):
    """Attacker-as-oracle grinds a random word that makes this bet win."""
    t = THRESH[game]
    w = start
    while True:
        if roll_for(w, client_seed) < t:
            return w
        w += 1

def find_losing_word(game, client_seed, start=0):
    t = THRESH[game]
    w = start
    while True:
        if roll_for(w, client_seed) >= t:
            return w
        w += 1

def bytecode(path_name):
    # path_name like "src/Casino.sol:Casino"
    return sh("forge", "inspect", path_name, "bytecode")
