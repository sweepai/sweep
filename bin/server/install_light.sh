# Clone the sweep repository
git_repo="http://github.com/sweepai/sweep"
git clone ${git_repo}

# Install Docker
docker_package="docker.io"
sudo apt install ${docker_package} -y
# Install Docker Compose
docker_compose_version="1.29.2"
sudo curl -L "https://github.com/docker/compose/releases/download/${docker_compose_version}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
# Make Docker Compose executable
sudo chmod +x /usr/local/bin/docker-compose
# Navigate to the sweep directory
cd sweep
# Remind the user to configure ngrok and how to proceed after setup
echo "Configure ngrok: https://dashboard.ngrok.com/get-started/setup"
echo "Then, use Docker to build and run the project."

# The following line is unnecessary as we're already executing `install_light.sh`
# curl -sSL https://raw.githubusercontent.com/sweepai/sweep/main/bin/server/install_light.sh | bash
