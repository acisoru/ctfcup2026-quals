#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# бинарник собирается в чистом Debian-контейнере, src/build.sh сам обновляет public/mmm.zip
"$here/src/build.sh"

echo "$here/public/mmm.zip"
