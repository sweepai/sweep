#!/bin/bash

# CYAN='\033[0;46m'
# CYAN='\033[1;36m'
CYAN=''
# WHITE='\033[1;37m'
WHITE='\033[1;37m'
# WHITE='\033[1;30m\033[47m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "\n${CYAN}${WHITE}### Starting Setup Script ###${NC}\n"

# Function to display message and exit when a command fails
exit_if_fail() {
  if [[ $? != 0 ]]; then
    echo -e "${RED}Error: $1${NC}"
    exit 1
  fi
}

echo -e "\n${CYAN}${WHITE}--> Checking for Python3, venv, and Docker...${NC}\n"
command -v python3 >/dev/null 2>&1 || { echo -e "${RED}Error: Python3 not found. Install it first.${NC}"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo -e "${RED}Error: Docker not found. Install it first.${NC}"; exit 1; }
python3 -c "import venv" 2>/dev/null || { echo -e "${RED}Error: venv not found. Install it first.${NC}"; exit 1; }

echo -e "\n${CYAN}${WHITE}--> Cloning repository...${NC}\n"
cd /tmp
rm -rf sweep
git clone https://github.com/sweepai/sweep.git --depth 1
exit_if_fail "Failed to clone repository."
cd sweep/sweepai/sandbox

echo -e "\n${CYAN}${WHITE}--> Setting up virtual environment...${NC}\n"
python3 -m venv venv
source venv/bin/activate
exit_if_fail "Failed to set up virtual environment."

echo -e "\n${CYAN}${WHITE}--> Installing Python dependencies...${NC}\n"
pip install -r requirements.txt
exit_if_fail "Failed to install Python dependencies."

echo -e "\n${CYAN}${WHITE}--> Installing PyInstaller...${NC}\n"
pip install pyinstaller
exit_if_fail "Failed to install PyInstaller."

echo -e "\n${CYAN}${WHITE}--> Creating standalone executable...${NC}\n"
PYTHONPATH=. pyinstaller --onefile --paths ./src cli.py
exit_if_fail "Failed to create standalone executable."

echo -e "\n${CYAN}${WHITE}--> Copying executable to home directory and /usr/bin...${NC}\n"
mv dist/cli dist/sweep-sandbox
cp -f dist/sweep-sandbox ~/
alias sweep-sandbox=~/sweep-sandbox

if [ -n "$BASH_VERSION" ]; then
    echo "alias sweep-sandbox='~/sweep-sandbox'" >> ~/.bashrc
elif [ -n "$ZSH_VERSION" ]; then
    echo "alias sweep-sandbox='~/sweep-sandbox'" >> ~/.zshrc
elif [ -n "$FISH_VERSION" ]; then
    echo "alias sweep-sandbox='~/sweep-sandbox'" >> ~/.config/fish/config.fish
else
    echo "Shell not supported."
fi
exit_if_fail "Failed to copy executable."

echo -e "\n${CYAN}${WHITE}--> Pulling sandbox Docker image...${NC}\n"
docker pull sweepai/sandbox:latest

exit_if_fail "Failed to pull sandbox Docker image."

deactivate

echo -e "\n${CYAN}${WHITE}### Setup Completed Successfully ###${NC}\n"

echo "To get started, run \`sweep-sandbox\` in the base of the repository you want to test Sweep's Sandbox execution runner in."
