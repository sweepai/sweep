# Start from the Jenkins LTS image
FROM jenkins/jenkins:lts

# Switch to root to install Docker and git
USER root

# Install git and apt-transport-https (necessary for Docker)
RUN apt-get update && \
    apt-get install -y git apt-transport-https ca-certificates curl gnupg lsb-release

# Set up Docker's official GPG key and the stable repository, then install Docker
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add - && \
    echo "deb [arch=amd64] https://download.docker.com/linux/debian $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y docker-ce docker-ce-cli containerd.io

# Add the Jenkins user to the Docker group
RUN usermod -aG docker jenkins

# Switch back to the Jenkins user
USER jenkins