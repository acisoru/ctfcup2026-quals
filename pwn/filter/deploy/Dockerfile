# ---- build stage: generate the model weights and compile the service ----
FROM ubuntu:22.04 AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev python3 python3-numpy make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY src/ /build/
RUN make clean || true && make

# ---- runtime stage ----
FROM ubuntu:22.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 ctf
WORKDIR /app
COPY --from=build /build/filter /app/filter
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/filter /app/entrypoint.sh

# The platform writes the real flag here (randomFlagFilename: false).
RUN echo 'ctfcup{local_build_flag_do_not_ship}' > /flag.txt && chmod 644 /flag.txt

EXPOSE 1337
USER ctf
ENTRYPOINT ["/app/entrypoint.sh"]
