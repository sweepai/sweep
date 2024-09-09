#!/bin/bash

# Remove old docker images only after 2 runs to allow for rollbacks.
# Docker images also need to finish processing their requests before they can be removed.
echo `docker ps`
containers_to_remove=$(docker ps -q | awk 'NR>3')

if [ ! -z "$containers_to_remove" ]; then
    echo "Removing old docker runs"
    docker rm -f $containers_to_remove
else
    echo "No old docker runs to remove"
fi

# Find next available port to deploy to
PORT=8081
is_port_free() {
    lsof -i :$1 > /dev/null
    return $?
}

while is_port_free $PORT; do
    ((PORT++))
done

echo "Found open port: $PORT"

# Start new docker container on the next available port
cd ~/sweep
docker build -t sweepai/sweep:latest -f Dockerfile.hosted .
container_id=$(docker run -v /mnt/caches:/mnt/caches -v --env-file .env -p $PORT:8080 -d sweepai/sweep:latest)
docker exec -it $container_id python tests/rerun_issue_direct.py --no-debug https://github.com/wwzeng1/landing-page/issues/114
echo "Running test on https://github.com/wwzeng1/landing-page/issues/114"

# Wait until webhook is available before rerouting traffic to it
echo "Waiting for server to start..."
while true; do
    curl --output /dev/null --silent --fail http://localhost:$PORT/health
    if [ $? -eq 0 ]; then
        echo "Received a good response!"
        break
    else
        printf '.'
        sleep 1
    fi
done

# Update the ngrok proxy to point to the new port
screen -list | grep -q "\bngrok\b"
SESSION_EXISTS=$?

if [ $SESSION_EXISTS -ne 0 ]; then
    screen -S ngrok -d -m
    echo creating new session
    sleep 1
fi

# Kill the ngrok process if it's already running
screen -S ngrok -X stuff $'\003'
sleep 1
screen -S ngrok -X stuff $'ngrok http --domain=sweep-prod.ngrok.dev '$PORT$'\n'

echo "Command sent to screen session on port: $PORT"
echo "To view the ngrok logs, run: screen -r ngrok"
