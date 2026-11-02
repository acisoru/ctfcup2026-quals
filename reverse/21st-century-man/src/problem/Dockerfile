FROM rust:1.95-slim-bookworm AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        pkg-config libudev-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src

ENV CARGO_HOME=/usr/local/cargo
RUN RUSTFLAGS="--remap-path-prefix=/usr/local/cargo=/cargo --remap-path-prefix=/usr/local/rustup=/rustc --remap-path-prefix=/build=/problem" \
    cargo build --release --locked \
    && strip target/release/problem

FROM scratch AS artifact
COPY --from=build /build/target/release/problem /problem
