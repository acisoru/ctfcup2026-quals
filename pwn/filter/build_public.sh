#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/deploy"
out="$here/public/filter.tar.gz"

[[ -d "$src" ]] || { echo "deploy/ not found: $src" >&2; exit 1; }

mkdir -p "$here/public"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# бинарь собирается в той же build-стадии, что и в деплое, чтобы раздатка совпадала с сервером
docker build -q --network host --target build -t filter-build "$src" >/dev/null
cid="$(docker create filter-build)"
docker cp "$cid:/build/filter" "$src/src/filter"
docker rm "$cid" >/dev/null

mkdir -p "$tmp/filter"
cp "$src/src/filter.c" "$src/src/model.h" "$src/src/gen_model.py" "$src/src/Makefile" "$src/src/filter" "$tmp/filter/"

rm -f "$out"
tar -C "$tmp" -czf "$out" filter

echo "$out"
