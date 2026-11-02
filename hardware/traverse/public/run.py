#!/usr/bin/env python3
"""
Runner for traverse.bin (Lattice iCE40 HX1K, iCEstick pinout).

The design talks 115200 8N1 UART on a 12 MHz clock:
  clk = pin 21, rx = pin 9 (FTDI -> FPGA), tx = pin 8 (FPGA -> FTDI).
Send a line terminated with '\\n', the design answers with one byte.

No board? The default mode simulates the bitstream itself: it is unpacked
with icestorm (iceunpack + icebox_vlog) into a gate-level Verilog netlist
and run under Icarus Verilog with a UART testbench.

  requirements (sim):  icestorm (iceunpack, icebox_vlog), iverilog (iverilog, vvp)
  requirements (hw):   iceprog, pyserial

usage:
  ./run.py 'ctfcup{...}'
  ./run.py --hw /dev/ttyUSB1 'ctfcup{...}'          # flash with iceprog first
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLK_HZ = 12_000_000
BAUD = 115200
DIV = CLK_HZ // BAUD  # clocks per UART bit

PCF = """set_io clk 21
set_io rx 9
set_io tx 8
set_io led 95
"""

TB = r"""
`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg rx = 1;
    wire tx, led;
    chip dut (.clk(clk), .rx(rx), .tx(tx), .led(led));
    always #41.667 clk = ~clk;  // 12 MHz

    localparam DIV = %(div)d;
    integer fin, fout, ch, b, k;
    reg [7:0] c;

    task send(input [7:0] v);
        begin
            rx = 0; repeat (DIV) @(posedge clk);
            for (b = 0; b < 8; b = b + 1) begin
                rx = v[b]; repeat (DIV) @(posedge clk);
            end
            rx = 1; repeat (DIV) @(posedge clk);
        end
    endtask

    // UART receiver on tx
    initial begin
        forever begin
            @(negedge tx);
            repeat (DIV / 2) @(posedge clk);
            for (k = 0; k < 8; k = k + 1) begin
                repeat (DIV) @(posedge clk);
                c[k] = tx;
            end
            repeat (DIV) @(posedge clk);
            $fwrite(fout, "%%c", c);
        end
    end

    initial begin
        fin = $fopen("input.bin", "rb");
        fout = $fopen("output.bin", "wb");
        repeat (64) @(posedge clk);
        ch = $fgetc(fin);
        while (ch >= 0) begin
            send(ch);
            ch = $fgetc(fin);
        end
        repeat (DIV * 30) @(posedge clk);
        $fclose(fout);
        $finish;
    end
endmodule
"""


def need(*tools):
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        sys.exit("missing tools: " + ", ".join(missing))


def fix_ports(net):
    # icebox_vlog uses an ANSI port list and then re-declares the ports as
    # wire/reg, which iverilog rejects; switch the header to non-ANSI style.
    m = re.search(r"module (\w+) \(([^)]*)\);", net)
    ports = [x.split() for x in m.group(2).split(",")]
    hdr = "module %s (%s);\n" % (m.group(1), ", ".join(n for _, n in ports))
    hdr += "".join("%s %s;\n" % (d, n) for d, n in ports)
    return net[:m.start()] + hdr + net[m.end():]


def run_sim(bitstream, data):
    need("iceunpack", "icebox_vlog", "iverilog", "vvp")
    with tempfile.TemporaryDirectory() as d:
        p = lambda name: os.path.join(d, name)
        with open(p("chip.pcf"), "w") as f:
            f.write(PCF)
        with open(p("tb.v"), "w") as f:
            f.write(TB % {"div": DIV})
        with open(p("input.bin"), "wb") as f:
            f.write(data)
        subprocess.run(["iceunpack", bitstream, p("chip.asc")], check=True)
        net = subprocess.run(["icebox_vlog", "-s", "-p", p("chip.pcf"), p("chip.asc")],
                             stdout=subprocess.PIPE, check=True).stdout.decode()
        with open(p("chip.v"), "w") as f:
            f.write(fix_ports(net))
        subprocess.run(["iverilog", "-o", p("sim"), p("tb.v"), p("chip.v")], check=True)
        subprocess.run(["vvp", "-n", p("sim")], cwd=d, check=True, stdout=subprocess.DEVNULL)
        with open(p("output.bin"), "rb") as f:
            return f.read().decode("latin-1")


def run_hw(port, data):
    import serial
    with serial.Serial(port, BAUD, timeout=1) as s:
        s.reset_input_buffer()
        s.write(data)
        return s.read(64).decode("latin-1")


def main():
    ap = argparse.ArgumentParser(description="run traverse.bin")
    ap.add_argument("line", help="string to send (a newline is appended)")
    ap.add_argument("--bitstream", default=os.path.join(HERE, "traverse.bin"))
    ap.add_argument("--hw", metavar="TTY", help="talk to a real board on this serial port")
    args = ap.parse_args()

    data = args.line.encode() + b"\n"
    if args.hw:
        out = run_hw(args.hw, data)
    else:
        out = run_sim(args.bitstream, data)
    print(out.strip())


if __name__ == "__main__":
    main()
