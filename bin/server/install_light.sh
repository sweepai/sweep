git clone http://github.com/sweepai/sweep
sudo apt install docker.io -y
sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
cd sweep
echo "Configure ngrok: https://dashboard.ngrok.com/get-started/setup"
echo "Then, run docker build/run commands."

# curl -sSL https://raw.githubusercontent.com/sweepai/sweep/main/bin/server/install_light.sh | bash
