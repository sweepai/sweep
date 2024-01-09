#!/bin/sh

echo PORT: ${PORT:-8080}
redis-server /app/redis.conf --bind 0.0.0.0 --port 6379 &
python sweepai.watch:app
