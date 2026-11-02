#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/deploy"
out="$here/public/codex-revenge.zip"

[[ -d "$src" ]] || { echo "deploy/ not found: $src" >&2; exit 1; }

mkdir -p "$here/public"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

rsync -a \
  --exclude 'node_modules' \
  --exclude '.DS_Store' \
  --exclude 'package-lock.json' \
  --exclude '.gitignore' \
  "$src"/ "$tmp"/codex-revenge/

rm -f "$out"
(
  cd "$tmp"
  zip -qr "$out" codex-revenge
)

echo "$out"
