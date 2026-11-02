#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$here/public/traverse.zip"

# пересборка битстрима: src/build.sh (Docker), затем копирование в public/
if [[ "${1:-}" == "--rebuild" ]]; then
  "$here/src/build.sh"
  cp "$here/src/traverse.bin" "$here/public/traverse.bin"
fi

for f in traverse.bin run.py; do
  [[ -f "$here/public/$f" ]] || { echo "public/$f not found" >&2; exit 1; }
done

rm -f "$out"
(
  cd "$here/public"
  zip -q "$out" traverse.bin run.py
)

echo "$out"
