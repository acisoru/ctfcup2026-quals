#!/bin/sh
# Build the release binary inside a clean Debian container and refresh
# public/mmm.zip. Nothing from the host (paths, compiler, user) ends up
# in the binary; the .comment section is stripped as well.
set -eu

cd "$(dirname "$0")"
docker build --network=host -t mmm-build .
cid=$(docker create mmm-build)
docker cp "$cid:/mmm.zip" ../public/mmm.zip
docker rm "$cid" >/dev/null
unzip -l ../public/mmm.zip
