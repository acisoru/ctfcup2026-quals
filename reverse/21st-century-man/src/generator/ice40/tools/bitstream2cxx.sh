#!/bin/sh
# bitstream2cxx.sh -- turn an iCE40 bitstream back into a C++ model.
#
#   bitstream.bin --iceunpack--> design.asc --icebox_vlog--> design.v
#                 --yosys (ice40 cell models + write_cxxrtl)--> design.cc
#
# usage: tools/bitstream2cxx.sh [-p pins.pcf] [-n module] bitstream.bin out_dir
#
#   -p pins.pcf   name the chip's pins like the pcf does (default: pcf/<device>_*.pcf
#                 for the device named in the bitstream); the harness expects
#                 clk, uart_rxd and uart_txd
#   -n module     name of the C++ top module (default: chip)
#
# out_dir receives design.asc, design.v, design.cc and the cxxrtl/ runtime
# headers, so `g++ -I out_dir` is all a harness needs (see tools/run_device.sh).
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
pcf=""
top=chip
while getopts "p:n:" opt; do
    case $opt in
        p) pcf=$OPTARG ;;
        n) top=$OPTARG ;;
        *) echo "usage: $0 [-p pins.pcf] [-n module] bitstream.bin out_dir" >&2; exit 2 ;;
    esac
done
shift $((OPTIND - 1))
[ $# -eq 2 ] || { echo "usage: $0 [-p pins.pcf] [-n module] bitstream.bin out_dir" >&2; exit 2; }
bin=$1
out=$2
mkdir -p "$out"

# 1. bitstream -> ASCII configuration
iceunpack "$bin" "$out/design.asc"
device=$(sed -n 's/^\.device \([a-z0-9]*\).*/\1/p' "$out/design.asc" | head -1)
echo "bitstream2cxx: device iCE40 $device"

if [ -z "$pcf" ]; then
    for cand in "$here"/pcf/*.pcf; do
        case "$(basename "$cand")" in
            "$device"_*|*"$device"*) pcf=$cand ;;
        esac
    done
    # icebox names devices 1k/5k/8k...; the pcf files are named after the part
    [ -n "$pcf" ] || case $device in
        5k) pcf=$here/pcf/up5k_sg48.pcf ;;
        8k) pcf=$here/pcf/hx8k_ct256.pcf ;;
    esac
fi
[ -n "$pcf" ] && [ -f "$pcf" ] || { echo "bitstream2cxx: no pcf for device '$device', pass -p" >&2; exit 1; }
echo "bitstream2cxx: pins from $pcf"

# 2. configuration -> Verilog netlist of SB_* primitives
icebox_vlog -s -n "$top" -p "$pcf" "$out/design.asc" > "$out/design.v"

# 3. netlist + Lattice cell models -> C++ (CXXRTL)
#    opt_mem drops the ROMs' never-enabled write ports first: a memory write
#    port with a constant clock makes write_cxxrtl crash (yosys 0.66 / 0.70).
datdir=$(yosys-config --datdir)
yosys -q -l "$out/yosys.log" -p "
    read_verilog -sv $datdir/ice40/cells_sim.v
    read_verilog $out/design.v
    hierarchy -top $top
    proc
    flatten
    opt_expr
    opt_clean
    opt_mem
    opt_clean
    write_cxxrtl -g0 -header $out/design.cc
" > /dev/null 2>&1 || { echo "bitstream2cxx: yosys failed, see $out/yosys.log" >&2; exit 1; }
rm -rf "$out/cxxrtl"
cp -r "$datdir/include/backends/cxxrtl/runtime/cxxrtl" "$out/cxxrtl"
printf '%s\n' "$top" > "$out/top.txt"
echo "bitstream2cxx: wrote $out/design.cc ($(wc -l < "$out/design.v") netlist lines, top module $top)"
