#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$here/public/21.zip"

# при --rebuild пересобирается проверялка в Docker (без следов хост-машины)
if [[ "${1:-}" == "--rebuild" ]]; then
  "$here/src/problem/build.sh"
fi

for f in README.txt g.bin problem; do
  [[ -f "$here/public/21/$f" ]] || { echo "public/21/$f not found" >&2; exit 1; }
done

rm -f "$out"
(
  cd "$here/public"
  zip -qr "$out" 21
)

echo "$out"
