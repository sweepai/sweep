#docker buildx build --platform linux/amd64 -t sweepai/sweep:latest .
docker run --platform linux/amd64 --env-file .env -p 8080:8080 sweepai/sweep:latest
