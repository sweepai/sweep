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
container_id=$(docker run -v $(pwd)/logn_logs:/app/logn_logs -v $(pwd)/sweep_docs:/app/sweep_docs --env-file .env -p $PORT:8080 -d sweepai/sweep:latest)
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


sudo iptables -t nat -L PREROUTING --line-numbers | grep 'REDIRECT' | tail -n1 | awk '{print $1}' | xargs -I {} sudo iptables -t nat -D PREROUTING {}
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port $PORT

echo "Command sent to screen session on port: $PORT"
echo "Success!"
