docker build -t sweepai/sweep:latest .
docker push sweepai/sweep:latest
docker build -t sweepai/sandbox -f sweepai/sandbox/Dockerfile.sandbox sweepai/sandbox/.
docker push sweepai/sandbox:latest
