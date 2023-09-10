#!/bin/bash

echo "Removing old docker runs"
echo `echo `docker ps``
echo Removed `docker ps -q | awk 'NR>4'`
docker ps -q | awk 'NR>4' | xargs docker rm -f

PORT=8080

# Function to check if a port is free
is_port_free() {
    lsof -i :$1 > /dev/null
    return $?
}

# Iterate to find a free port
while is_port_free $PORT; do
    ((PORT++))
done

echo
echo "Found open port: $PORT"

# Start new docker container
cd ~/sweep
# docker build -t sweepai/sweep:latest .
docker compose build
docker run --env-file .env -p $PORT:8080 -d sweepai/sweep:latest
docker run --env-file .env -p 8081:8080 -d sweepai/sandbox-web

# Check if the "ngrok" screen session exists
screen -list | grep -q "\bngrok\b"
SESSION_EXISTS=$?

# If it doesn't exist, create a detached screen session named "ngrok"
if [ $SESSION_EXISTS -ne 0 ]; then
    screen -S ngrok -d -m
    echo creating new session
    sleep 1
fi

echo $SESSION_EXISTS

# Send the ngrok command to the "ngrok" screen session
screen -S ngrok -X stuff $'\003'
sleep 1
screen -S ngrok -X stuff $'ngrok http --domain=sweep-prod.ngrok.dev '$PORT$'\n'

echo
echo "Command sent to screen session on port: $PORT"
echo "To view the ngrok logs, run: screen -r ngrok"
