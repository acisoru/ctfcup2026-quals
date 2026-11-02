#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/src"
out="$here/public/weird-rsa.tar.gz"

for f in chall.sage output.txt; do
  [[ -f "$src/$f" ]] || { echo "src/$f not found" >&2; exit 1; }
done

mkdir -p "$here/public"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/weird-rsa"
cp "$src/chall.sage" "$src/output.txt" "$tmp/weird-rsa/"

rm -f "$out"
tar -C "$tmp" -czf "$out" weird-rsa

echo "$out"
