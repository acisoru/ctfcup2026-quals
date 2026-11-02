#!/bin/sh
set -e

mkdir -p /data
chown -R app:app /data

# Flag at /flag.txt. The vulnerable ERB render executes as the `app` user,
# so the intended RCE solution reads it as `app`. Owned by app, mode 0400:
# not world-readable, but reachable once you have code exec in the web app.
chown app:app /flag.txt
chmod 0400 /flag.txt

su -s /bin/sh app -c 'cd /app && POKEBOX_DB=/data/pokebox.db ruby app/initdb.rb'

exec su -s /bin/sh app -c 'cd /app && POKEBOX_DB=/data/pokebox.db SECRET=$(head -c32 /dev/urandom | od -An -tx1 | tr -d " \n") bundle exec puma -b tcp://0.0.0.0:8000 config.ru'
