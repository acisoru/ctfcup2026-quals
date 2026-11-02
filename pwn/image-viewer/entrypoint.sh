#!/bin/sh
# ASLR stays enabled; the service leaks a PIE pointer and a heap pointer.
exec /app/service
