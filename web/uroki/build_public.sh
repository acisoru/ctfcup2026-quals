#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/deploy"
out="$here/public/uroki.zip"

[[ -d "$src" ]] || { echo "deploy/ not found: $src" >&2; exit 1; }

mkdir -p "$here/public"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

rsync -a \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache' \
  --exclude 'entrypoint.sh' \
  "$src"/ "$tmp"/uroki/

python3 - "$tmp/uroki/Dockerfile" <<'EOF'
import sys

path = sys.argv[1]
s = open(path).read()
s = s.replace(
    "COPY entrypoint.sh /entrypoint.sh",
    "# entrypoint.sh отсутствует в материалах\n"
    "COPY entrypoint.sh /entrypoint.sh",
)
open(path, "w").write(s)
EOF

rm -f "$out"
(
  cd "$tmp"
  zip -qr "$out" uroki
)

echo "$out"
