#!/usr/bin/env bash
# Build the handout archive given to participants (the deploy/ source tree).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/deploy"
out="$here/public/compuuuter.zip"

[[ -d "$src" ]] || { echo "deploy/ not found: $src" >&2; exit 1; }

mkdir -p "$here/public"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/compuuuter"
cp -r "$src"/. "$tmp/compuuuter/"
find "$tmp/compuuuter" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$tmp/compuuuter" -name '.DS_Store' -delete 2>/dev/null || true

rm -f "$out"
(
  cd "$tmp"
  zip -qr "$out" compuuuter
)

echo "$out"
