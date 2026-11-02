#!/usr/bin/env bash
# Воспроизводимая сборка проверялки `problem` в Docker: все пути к cargo-registry
# и rustc remap'ятся, так что в бинаре не остаётся следов хост-машины.
# Результат копируется в раздатку public/21/problem.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$here/../../public/21/problem"

docker build --network host -q --target build -t problem-build "$here" >/dev/null
cid="$(docker create problem-build)"
docker cp "$cid:/build/target/release/problem" "$out"
docker rm "$cid" >/dev/null
chmod +x "$out"

echo "$out"
