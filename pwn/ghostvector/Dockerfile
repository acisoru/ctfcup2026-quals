FROM docker.io/library/fedora:43

RUN dnf -y --setopt=install_weak_deps=False install \
        openssl qemu-system-riscv-core \
    && dnf clean all

ADD ghostvector-runtime.tar.gz /opt/ghostvector/
WORKDIR /opt/ghostvector

EXPOSE 2222/tcp
ENV SSH_PORT=2222 \
    SSH_LISTEN_ADDRESS=0.0.0.0 \
    FLAG_FILE=/flag.txt \
    FLAG_FILE_WAIT_SECONDS=120 \
    SSH_PASSWORD=user:password

ENTRYPOINT ["/opt/ghostvector/run.sh"]
