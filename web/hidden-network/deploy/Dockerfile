FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# The platform only needs to build one ordinary image and publish one port.
# The Linux guest inside this image owns the Docker networks and /dev/net/tun.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       qemu-system-x86 \
       qemu-utils \
    && rm -rf /var/lib/apt/lists/*

RUN install -d -m 0755 /opt/ctf-vm
COPY challenge.qcow2 /opt/ctf-vm/challenge.qcow2
COPY run_qemu.sh /usr/local/bin/run-ctf-vm

RUN chmod 0755 /usr/local/bin/run-ctf-vm \
    && test -x /usr/bin/qemu-system-x86_64 \
    && test -x /usr/bin/qemu-img

EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/run-ctf-vm"]
