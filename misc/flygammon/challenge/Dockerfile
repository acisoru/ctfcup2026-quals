# Challenge image: anvil + league contracts + fly daemon + single-port front door.
# Build context is the task directory (misc/flygammon) so the flygammon crate,
# daemon and contracts are all in scope:
#
#   docker build -f challenge/Dockerfile -t cr.yandex/crp0n0k1igdhl8p66pc9/ctfcup-flygammon .
#
# The flag: on the platform the real flag is written to /flag.txt
# the FLAG env below is only a local fallback, served by the
# front door once isSolved() is true.

# ---- stage 1: build the Rust fly daemon ----
FROM rust:1-bookworm AS rustbuild
WORKDIR /src
COPY flygammon /src/flygammon
COPY daemon /src/daemon
WORKDIR /src/daemon
RUN cargo build --release

# ---- final image ----
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 openssl ca-certificates libssl3 curl git \
    && rm -rf /var/lib/apt/lists/*

# Foundry (anvil / forge / cast) via the official installer.
ENV PATH="/root/.foundry/bin:${PATH}"
RUN curl -L https://foundry.paradigm.xyz | bash && foundryup

WORKDIR /app
# fly daemon
COPY --from=rustbuild /src/daemon/target/release/flygammon-daemon /app/flygammon-daemon
# league contracts (precompiled so deploy is instant)
COPY challenge/project /app/project
RUN cd /app/project && forge build
# model (daemon uses the .mpk checkpoint internally)
COPY flygammon/attempts/h80_i100_distill/flygammon_best.mpk /app/flygammon_best.mpk
# python tooling + services
COPY tools/dlp.py tools/make_instance_params.py /app/tools/
# single-port front door (async Rust proxy: no thread-per-connection growth)
COPY --from=rustbuild /src/daemon/target/release/flygammon-proxy /app/flygammon-proxy
COPY challenge/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV WIN_N=15 COMMIT_BUDGET=80 FACTOR_BITS=20
EXPOSE 8545
ENTRYPOINT ["/app/entrypoint.sh"]
