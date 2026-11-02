#!/bin/sh
set -e

mkdir -p /data /data/mq /data/uploads
chown -R app:app /data

chown app:app /flag.txt
chmod 0000 /flag.txt

su -s /bin/sh app -c 'cd /app && python3 -c "from app import db; db.init_db()"'

exec supervisord -c /etc/supervisord.conf
