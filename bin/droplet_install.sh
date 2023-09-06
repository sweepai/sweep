curl https://pyenv.run | bash
{
echo 'export PYENV_ROOT="$HOME/.pyenv"'
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"'
echo 'eval "$(pyenv init -)"'
} > ~/.bash_profile
sed -i '1i\
export PATH="/root/.local/bin:$PATH"\
eval "$(pyenv virtualenv-init -)"\
' ~/.bashrc
source ~/.bash_profile
source ~/.bashrc

# install to bashrc and bash_profile
sudo apt-get install -y build-essential libssl-dev zlib1g-dev libbz2-dev \
libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
xz-utils tk-dev libffi-dev liblzma-dev python3-openssl git
sudo apt update
sudo apt install -y gcc g++

# Install python 3.11.5
pyenv install 3.11.5
cd ~/sweep
pyenv local 3.11.5

# Install poetry
curl -sSL https://install.python-poetry.org | python3 -
poetry env use /root/.pyenv/versions/3.11.5/bin/python
poetry shell

# Install redis cache
apt-get update
apt-get install redis
sudo systemctl stop redis

# Install ngrok for deployment
snap install ngrok
