#!/bin/bash

docker pull sweepai/sweep:latest
docker kill $(docker ps -q)
docker run --env-file .env -p 8080:8080 -d sweepai/sweep:latest
