# !/bin/bash

# Remove old docker images only after 2 runs to allow for rollbacks.
# Docker images also need to finish processing their requests before they can be removed.

docker pull sweepai/sweep:latest
docker pull sweepai/sweep-chat:latest

echo `docker ps`
containers_to_remove=$(docker ps -q --filter "ancestor=sweepai/sweep" | awk 'NR>2')
containers_to_remove+=" $(docker ps -q --filter "ancestor=sweepai/sweep-chat" | awk 'NR>2')"

if [ ! -z "$containers_to_remove" ]; then
    echo "Removing old docker runs"
    echo "$containers_to_remove" | while read -r container; do
        if [ ! -z "$container" ]; then
            docker kill "$container"
            docker rm "$container"
        fi
    done
else
    echo "No old docker runs to remove"
fi

# Find next available port to deploy to
PORT=8081
is_port_free() {
    if curl -s http://localhost:$1 > /dev/null; then
        return 0 # Port is in use
    else
        return 1 # Port is free
    fi
}

FRONTEND_PORT=$(($PORT - 8000))

while is_port_free $PORT || is_port_free $FRONTEND_PORT; do
    ((PORT++))
    FRONTEND_PORT=$(($PORT - 8000))
done

echo "Found open port: $PORT"

NETWORK_NAME="sweep_network_${PORT}_${TIMESTAMP}"

if [ ! -f .env ]; then
    echo "Error: .env file not found" >&2
    exit 1
fi

if ! docker network inspect $NETWORK_NAME >/dev/null 2>&1; then
    docker network create $NETWORK_NAME || { echo "Failed to create network"; exit 1; }
fi

BACKEND_CONTAINER_NAME="sweep_backend_${PORT}"
docker run --name $BACKEND_CONTAINER_NAME --env-file .env -p $PORT:8080 -v $PWD/caches:/mnt/caches --network $NETWORK_NAME -d sweepai/sweep:latest

BACKEND_URL="http://${BACKEND_CONTAINER_NAME}:8080"
docker run --env-file .env -e BACKEND_URL=$BACKEND_URL -p $FRONTEND_PORT:3000 -v $PWD/caches:/mnt/caches --network $NETWORK_NAME -d sweepai/sweep-chat:latest

echo "Backend accessible at: http://localhost:$PORT"
echo "Frontend accessible at: http://localhost:$FRONTEND_PORT"

# Wait until webhook is available before rerouting traffic to it
echo "Waiting for server to start..."
while true; do
    curl --output /dev/null --silent --head --fail http://localhost:$PORT/health
    result=$?
    if [[ $result -eq 0 || $result -eq 22 ]]; then
        echo "Received a good response!"
        break
    else
        printf '.'
        sleep 5
    fi
done

# Reroute traffic to new docker container
sudo iptables -t nat -L PREROUTING --line-numbers | grep 'REDIRECT' | tail -n1 | awk '{print $1}' | xargs -I {} sudo iptables -t nat -D PREROUTING {}
sudo iptables -t nat -L PREROUTING --line-numbers | grep 'REDIRECT' | tail -n1 | awk '{print $1}' | xargs -I {} sudo iptables -t nat -D PREROUTING {}

sudo iptables -t nat -A PREROUTING -p tcp --dport ${SWEEP_PORT:-8080} -j REDIRECT --to-port $PORT
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port $FRONTEND_PORT

containers_to_remove=$(docker ps -q --filter "ancestor=sweepai/sweep" | awk 'NR>1')
containers_to_remove+=" $(docker ps -q --filter "ancestor=sweepai/sweep-chat" | awk 'NR>1')"

# kill previous docker image after 20 min
if [ ! -z "$containers_to_remove" ]; then
    (
        sleep 1200
        echo "$containers_to_remove" | while read -r container; do
            if [ ! -z "$container" ]; then
                docker kill "$container"
            fi
        done
    ) &
    echo "Scheduled removal of old containers after 20 minutes"
else
    echo "No old containers to remove after 20 minutes"
fi

echo "Command sent to screen session on port: $PORT"
echo "Success!"
