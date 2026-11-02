# Builder image for the iCE40 evaluator: yosys, nextpnr-ice40, icestorm
# (icepack / iceunpack / icebox_vlog), iverilog, verilator and a C++ compiler.
#
#   docker build -t g-ice40 .
#   docker run --rm -v "$PWD/..:/work" -w /work/ice40 g-ice40 make NATIVE=1 ...
#
# The Makefile wraps this for you: `make` runs every tool step through the image.
#
# The FPGA tools come from a pinned YosysHQ OSS CAD Suite release, so the
# bitstream is reproducible; OSS_CAD_SUITE can be overridden at build time.
FROM debian:trixie-slim

ARG OSS_CAD_SUITE=2026-10-19
ARG OSS_CAD_SUITE_FILE=oss-cad-suite-linux-x64-20261019.tgz

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils \
        build-essential g++ make \
        python3 python3-numpy python3-serial \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/oss.tgz \
        "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_SUITE}/${OSS_CAD_SUITE_FILE}" \
 && mkdir -p /opt && tar -C /opt -xzf /tmp/oss.tgz && rm /tmp/oss.tgz

ENV PATH="/opt/oss-cad-suite/bin:${PATH}"

# sanity check at build time: every tool the Makefile calls must be here
RUN yosys -V && nextpnr-ice40 --version && icepack -h >/dev/null 2>&1 ; iceunpack -h >/dev/null 2>&1 ; \
    icebox_vlog --help >/dev/null && iverilog -V | head -1 && verilator --version && g++ --version | head -1

WORKDIR /work/ice40
