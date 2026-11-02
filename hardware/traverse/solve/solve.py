#!/usr/bin/env python3
# Solver: turn the bitstream back into a gate-level netlist (iceunpack +
# icebox_vlog), then use the simulation as an oracle that exposes the
# internal flip-flops. Strings that fall into the DFA's dead state all leave
# the same register snapshot (except for the UART byte registers), so we can
# walk the DFA breadth-first, keeping only prefixes whose snapshot is not dead.
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(HERE, "..", "public"))
import run  # noqa: E402

BIT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "public", "traverse.bin")
ALPHABET = b"0123456789abcdef{}tup"

TB = r"""
`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg rx = 1;
    wire tx, led;
    chip dut (.clk(clk), .rx(rx), .tx(tx), .led(led));
    always #41.667 clk = ~clk;

    localparam DIV = %(div)d;
    integer fin, fout, ch, b;

    task send(input [7:0] v);
        begin
            rx = 0; repeat (DIV) @(posedge clk);
            for (b = 0; b < 8; b = b + 1) begin
                rx = v[b]; repeat (DIV) @(posedge clk);
            end
            rx = 1; repeat (DIV) @(posedge clk);
        end
    endtask

    // one probe per input line: send it, snapshot all FFs, then send '\n'
    // (returns the DFA to its start state) and report the led
    initial begin
        fin = $fopen("probes.txt", "rb");
        fout = $fopen("snap.txt", "w");
        repeat (64) @(posedge clk);
        ch = $fgetc(fin);
        while (ch >= 0) begin
            if (ch == 10) begin
                repeat (DIV * 4) @(posedge clk);
                $fwrite(fout, "%%b ", {%(regs)s});
                send(10);
                repeat (DIV * 2) @(posedge clk);
                $fwrite(fout, "%%b\n", led);
            end else
                send(ch);
            ch = $fgetc(fin);
        end
        $fclose(fout);
        $finish;
    end
endmodule
"""

work = tempfile.mkdtemp()
p = lambda n: os.path.join(work, n)
open(p("chip.pcf"), "w").write(run.PCF)
subprocess.run(["iceunpack", BIT, p("chip.asc")], check=True)
net = subprocess.run(["icebox_vlog", "-s", "-p", p("chip.pcf"), p("chip.asc")],
                     stdout=subprocess.PIPE, check=True).stdout.decode()
open(p("chip.v"), "w").write(run.fix_ports(net))
regs = [r for line in net.splitlines() if line.startswith("reg ")
        for r in re.findall(r"(\w+) = ", line)]
open(p("tb.v"), "w").write(TB % {"div": run.DIV, "regs": ", ".join("dut." + r for r in regs)})
subprocess.run(["iverilog", "-o", p("sim"), p("tb.v"), p("chip.v")], check=True)


def probe(strings):
    open(p("probes.txt"), "wb").write(b"".join(s + b"\n" for s in strings))
    subprocess.run(["vvp", "-n", p("sim")], cwd=work, check=True, stdout=subprocess.DEVNULL)
    res = [l.split() for l in open(p("snap.txt"))]
    return [(int(a, 2), b == "1") for a, b in res]


# calibration: '~' kills the DFA from the start state, so the snapshots of
# '~' + c differ only in registers that hold the last received byte
dead = probe([b"~" + bytes([c]) for c in ALPHABET])
mask = 0
for s, _ in dead:
    mask |= s ^ dead[0][0]
mask = ~mask
dead_sig = dead[0][0] & mask
print("state-ish FFs: %d of %d" % (bin(mask & ((1 << len(regs)) - 1)).count("1"), len(regs)))

frontier = [b""]
while frontier:
    cand = [f + bytes([c]) for f in frontier for c in ALPHABET]
    res = probe(cand)
    for s, (sig, ok) in zip(cand, res):
        if ok:
            print(s.decode())
            sys.exit(0)
    frontier = sorted({s for s, (sig, _) in zip(cand, res) if sig & mask != dead_sig})
    print(len(frontier[0]) if frontier else "-", [x.decode() for x in frontier])
sys.exit("not found")
