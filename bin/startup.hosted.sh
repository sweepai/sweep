#!/bin/sh

echo PORT: ${PORT:-8080}
redis-server /app/redis.conf --bind 0.0.0.0 --port 6379 &
uvicorn sweepai.api:app --host 0.0.0.0 --port ${PORT:-8080} --workers 30
