#!/bin/sh
# Reproducible build of the bitstream with the open-source iCE40 toolchain
# (yosys + nextpnr-ice40 + icestorm) inside Docker.
set -e
cd "$(dirname "$0")"
docker build --network host -q -t traverse-build . >/dev/null
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/work" traverse-build make
