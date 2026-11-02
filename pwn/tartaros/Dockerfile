FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends qemu-system-x86 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY tartaros.iso /app/tartaros.iso
COPY flag.img /app/flag.img
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod 0755 /app/entrypoint.sh

ENV FLAG_IMG=/app/flag.img

EXPOSE 22

ENTRYPOINT ["/app/entrypoint.sh"]
