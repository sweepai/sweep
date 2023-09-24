run_until_success() {
    local cmd="$1"
    until $cmd; do
        echo "Command failed, retrying in 5 seconds..."
        sleep 5
    done
}

run_until_success "sudo apt update"
run_until_success "sudo apt install -y gcc g++ curl"
run_until_success "sudo apt-get update"
run_until_success "sudo apt-get install -y redis build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python3-openssl git"
run_until_success "sudo systemctl stop redis"
run_until_success "snap install ngrok"
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common -y && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add - && sudo add-apt-repository -y "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" && sudo apt update -y && sudo apt install docker-ce -y && sudo systemctl enable docker && sudo systemctl start docker && sudo usermod -aG docker ${USER}

curl https://pyenv.run | bash
{
echo 'export PYENV_ROOT="$HOME/.pyenv"'
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"'
echo 'eval "$(pyenv init -)"'
echo '. ~/.bashrc'
} > ~/.bash_profile
sed -i '1i\
export PATH="/root/.local/bin:$PATH"\
eval "$(pyenv virtualenv-init -)"\
alias activate='\''source $(poetry env info --path)/bin/activate'\''\
' ~/.bashrc
source ~/.bash_profile
source ~/.bashrc

# Install python 3.11.5
pyenv install 3.11.5
cd ~/sweep
pyenv local 3.11.5

# Install poetry
curl -sSL https://install.python-poetry.org | python3 -
poetry env use /root/.pyenv/versions/3.11.5/bin/python
poetry shell

# Install with this command, pressing only enter when prompted:
# git clone https://github.com/sweepai/sweep ~/sweep && . sweep/bin/install_full.sh

# Afterwards, run:
# - poetry install
# - ngrok config (https://dashboard.ngrok.com/get-started/setup)
# - copy .envs

# To get into poetry shell, run `activate` from the sweep directory.
