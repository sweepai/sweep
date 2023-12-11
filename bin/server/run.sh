# Run the Docker container using environment variables and port mapping
env_file='.env'
host_port=8080
container_port=8080
image_name='sweepai/sweep:latest'
docker run --env-file ${env_file} -p ${host_port}:${container_port} -d ${image_name}
