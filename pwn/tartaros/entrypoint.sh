#!/bin/sh
set -eu

FLAG_IMG="${FLAG_IMG:-/app/flag.img}"

if [ -c /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
    set -- -enable-kvm -cpu host
else
    set -- -accel tcg,thread=multi -cpu max
fi

exec qemu-system-x86_64 \
    -name tartaros \
    "$@" \
    -smp 1 \
    -m 2048 \
    -cdrom /app/tartaros.iso \
    -boot d \
    -drive file="$FLAG_IMG",format=raw,if=none,id=flag \
    -device ide-hd,drive=flag \
    -netdev user,id=net0,hostfwd=tcp:0.0.0.0:22-:22,restrict=on \
    -device e1000,netdev=net0 \
    -display none \
    -monitor none \
    -serial file:/tmp/serial.log \
    -no-reboot \
    -snapshot
