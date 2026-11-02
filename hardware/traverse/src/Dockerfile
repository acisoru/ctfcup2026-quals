FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        yosys nextpnr-ice40 fpga-icestorm iverilog python3 make \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
