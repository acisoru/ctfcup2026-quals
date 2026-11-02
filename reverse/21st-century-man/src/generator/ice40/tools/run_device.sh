#!/bin/sh
# run_device.sh -- compile the C++ model made by tools/bitstream2cxx.sh together
# with the UART harness and run it as a serial device on a pseudo-terminal.
#
# usage: tools/run_device.sh [-c CLK_HZ] [-b BAUD] [-l link] [-s] cxx_dir
#
#   -c CLK_HZ   clock the bitstream was built for (default 200000000)
#   -b BAUD     baud rate it was built for          (default 921600)
#   -l link     also create a symlink to the pty at this path (e.g. /tmp/g_uart)
#   -s          talk on stdin/stdout instead of a pty
#   cxx_dir     output directory of bitstream2cxx.sh (design.cc, cxxrtl/, top.txt)
#
# The binary is cached as cxx_dir/device and rebuilt when design.cc is newer.
# Compiled with -Ofast (override with CXXFLAGS); the compile takes a while.
# The device prints the pty path on its first stdout line, e.g.
#   python3 ../dsp58/host/g_client.py --port $(head -1 pty.txt) --baud 921600 --at 0.3,0.4
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
clk=200000000
baud=921600
link=""
stdio=""
while getopts "c:b:l:s" opt; do
    case $opt in
        c) clk=$OPTARG ;;
        b) baud=$OPTARG ;;
        l) link=$OPTARG ;;
        s) stdio="--stdio" ;;
        *) echo "usage: $0 [-c CLK_HZ] [-b BAUD] [-l link] [-s] cxx_dir" >&2; exit 2 ;;
    esac
done
shift $((OPTIND - 1))
[ $# -eq 1 ] || { echo "usage: $0 [-c CLK_HZ] [-b BAUD] [-l link] [-s] cxx_dir" >&2; exit 2; }
dir=$1
top=$(cat "$dir/top.txt" 2>/dev/null || echo chip)

if [ ! -x "$dir/device" ] || [ "$dir/design.cc" -nt "$dir/device" ] || [ "$here/sim/device_main.cc" -nt "$dir/device" ]; then
    echo "run_device: compiling $dir/design.cc (this takes a while)" >&2
    ${CXX:-g++} -std=c++17 ${CXXFLAGS:--Ofast} -w -I "$dir" -DDESIGN_TOP="$top" \
        -o "$dir/device" "$here/sim/device_main.cc" "$dir/design.cc" -lutil
fi

set -- --clk-hz "$clk" --baud "$baud"
[ -n "$link" ] && set -- "$@" --link "$link"
[ -n "$stdio" ] && set -- "$@" $stdio
exec "$dir/device" "$@"
