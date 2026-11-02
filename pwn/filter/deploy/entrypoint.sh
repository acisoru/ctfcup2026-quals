#!/bin/sh
# Each connection gets its own forked process; the socket is dup'd onto the
# child's stdin/stdout/stderr so a spawned shell talks over the connection.
exec socat -T120 TCP-LISTEN:1337,reuseaddr,fork EXEC:"/app/filter",stderr
