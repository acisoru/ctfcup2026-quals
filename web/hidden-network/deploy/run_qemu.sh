#!/bin/sh
set -eu

base_image=/opt/ctf-vm/challenge.qcow2
runtime_image=/tmp/ctf-vm-runtime.qcow2
flag_path="${FLAG_FILE:-/flag.txt}"
flag_value="${LOL_FLAG:-}"
temporary_flag=""
qemu_accel="${QEMU_ACCEL:-kvm}"

# Local runners can expose /dev/kvm for a near-native guest.  Keep a safe TCG
# fallback for platforms that only allow build/image/ports and do not pass the
# KVM device into the outer container.
if [ "${qemu_accel}" = "kvm" ] && [ ! -e /dev/kvm ]; then
  echo 'QEMU: /dev/kvm is unavailable; falling back to TCG' >&2
  qemu_accel=tcg
fi

cleanup() {
  if [ -n "${temporary_flag}" ]; then
    rm -f "${temporary_flag}"
  fi
  rm -f "${runtime_image}"
}
trap cleanup EXIT INT TERM

if [ ! -r "${base_image}" ]; then
  echo "guest qcow2 image is missing: ${base_image}" >&2
  exit 1
fi

# The platform normally creates /flag.txt before starting the service. Keep a
# short grace period for runners that copy it just after container creation.
# Local runs may provide LOL_FLAG or the conventional FLAG environment value.
if [ -z "${flag_value}" ]; then
  flag_value="${FLAG:-}"
fi

if [ ! -r "${flag_path}" ] && [ -z "${flag_value}" ]; then
  for _ in $(seq 1 15); do
    [ -r "${flag_path}" ] && break
    sleep 1
  done
fi

if [ ! -r "${flag_path}" ]; then
  temporary_flag=$(mktemp)
  flag_path="${temporary_flag}"
  printf '%s\n' "${flag_value}" >"${flag_path}"
fi

# Keep the packaged base image immutable. Docker-in-the-guest writes its
# layers and runtime state into this throw-away qcow2 overlay.
qemu-img create -q -f qcow2 -F qcow2 -b "${base_image}" "${runtime_image}"

exec qemu-system-x86_64 \
  -name ctf-hidden-network \
  -machine "pc,accel=${qemu_accel}" \
  -cpu max \
  -m "${QEMU_MEMORY:-4096M}" \
  -smp "${QEMU_SMP:-4}" \
  -drive "file=${runtime_image},if=virtio,format=qcow2,cache=unsafe" \
  -netdev "user,id=net0,hostfwd=tcp:0.0.0.0:8080-10.0.2.15:8080" \
  -device virtio-net-pci,netdev=net0 \
  -fw_cfg "name=opt/ctf/flag,file=${flag_path}" \
  -nographic \
  -display none \
  -serial stdio \
  -monitor none
