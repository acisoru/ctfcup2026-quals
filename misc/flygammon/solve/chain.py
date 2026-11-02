"""Thin chain I/O via the `cast` CLI (Foundry). Avoids web3/signing deps."""

import subprocess


class Chain:
    def __init__(self, rpc, addr, pk=None):
        self.rpc = rpc
        self.addr = addr
        self.pk = pk

    def _run(self, cmd):
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode != 0:
            raise RuntimeError(" ".join(cmd) + "\n" + out.stderr.strip())
        return out.stdout.strip()

    def call(self, sig, *args):
        cmd = ["cast", "call", self.addr, sig] + [str(a) for a in args] + ["--rpc-url", self.rpc]
        return self._run(cmd)

    def send(self, sig, *args):
        cmd = (
            ["cast", "send", self.addr, sig]
            + [str(a) for a in args]
            + ["--rpc-url", self.rpc, "--private-key", self.pk, "--gas-limit", "30000000000"]
        )
        return self._run(cmd)

    def call_uint(self, sig):
        s = self.call(sig)
        # cast may append scientific notation in brackets; take the first token
        return int(s.split()[0])

    def call_bool(self, sig):
        return self.call(sig).split()[0] == "true"


def arr(xs):
    return "[" + ",".join(str(int(x)) for x in xs) + "]"
