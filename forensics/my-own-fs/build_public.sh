#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# собирает myfs, генерирует новый случайный образ и пишет public/my-own-fs.zip
# нужны cargo, fusermount3 и Pillow
python3 "$here/src/gen.py"
