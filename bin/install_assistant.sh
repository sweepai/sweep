#!/bin/zsh

RED="\033[0;31m"
GREEN="\033[1;32m"
BLUE="\033[1;34m"
BLUE="\033[1;35m"
YELLOW="\033[1;33m"
NC="\033[0m" # No Color

echo -e "


                         @@@@@@@@@@@@@@@@@@@%*
                     #@@@                    @+
                   @@                       @
                 =@             @@@       @@
                @@              @  @=   @-
                @               @@ @*   @
               @                +@ @%   @
               %@               *@ @=   @@
               @@@@@            =% %  @@
              @@@@@@@@@@@@@@@@@@@  @@@@@
              @@@@@@@@@@@@@@@@@@@  @@@@@@
             @@@@@@@@@@@@@@@@@@@@  @@@@@@#                  ${BLUE}Sweep AI Assistant${NC}
             @@@   %@@@   @@@@@@  @@@@@@@@@
             @@@    @@%   *@@@@# @@@@@@@@@@@@@@
             @@@   @@@@   @@@@@ @@@@@@@@@@@@@@
             @@@@@@@@@@@@@@@@@  @@@@@@@@@@@@@               https://docs.sweep.dev/assistant
              @@@@@@@@@@@@@@@@  @@@@@@@@@@@@
               @@@@@@@@@@@@@@  @@@@@@@@@@@@
                #@@@@@@@@@@@    @@@@@@@@@@
                   @@@@@@@    @@@@@@@@@*
                      @*    @@@@@@@@
           @%*@@@@@@@       %
           #@               #@
             @            @ @@
              @@         @# @*
                @@*      @  @
                  %@@@# @@  @
                      %@@@@@

                                                            "

NO_TELEMETRY=false

for arg in "$@"
do
    if [ "$arg" = "--no-telemetry" ]; then
        NO_TELEMETRY=true
    fi
done

send_event() {
    if [ "$NO_TELEMETRY" = true ]; then
        return 0
    fi

    local event_name=$1
    local timestamp=$(date +%s 2>/dev/null)
    local distinct_id="$(whoami 2>/dev/null)@$(hostname 2>/dev/null)"

    curl -v -L --header "Content-Type: application/json" -d '{
        "event": "'"${event_name}"'",
        "api_key": "phc_CnzwIB0W548wN4wEGeRuxXqidOlEUH2AcyV2sKTku8n",
        "distinct_id": "'"${distinct_id}"'",
        "timestamp": "'"${timestamp}"'",
        "properties": {
            "email": "'"$(git config --global user.email 2>/dev/null || echo "N/A")"'",
            "whoami": "'"$(whoami 2>/dev/null)"'",
            "hostname": "'"$(hostname 2>/dev/null)"'",
            "os": "'"$(uname -s 2>/dev/null)"'",
            "os_version": "'"$(uname -r 2>/dev/null)"'",
            "os_arch": "'"$(uname -m 2>/dev/null)"'",
            "os_platform": "'"$(uname -o 2>/dev/null)"'",
            "os_release": "'"$(uname -v 2>/dev/null)"'",
            "os_distribution": "'"$(lsb_release -d 2>/dev/null | cut -f2)"'",
            "os_codename": "'"$(lsb_release -c 2>/dev/null | cut -f2)"'",
            "node_version": "'"$(node -v 2>/dev/null || echo "N/A")"'",
            "npm_version": "'"$(npm -v 2>/dev/null || echo "N/A")"'",
            "nvm_version": "'"$(nvm --version 2>/dev/null || echo "N/A")"'",
            "ip_address": "'"$(ip addr show 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | cut -d/ -f1 | head -n1 || echo "N/A")"'"
            "timestamp": "'"${timestamp}"'",
        }
    }' https://app.posthog.com/capture/ > /dev/null 2>&1
}

send_event "assistant_install_started"

# Check if npm is installed
if ! command -v npm &> /dev/null
then
    echo -e "${RED}npm could not be found, please install npm and try again.${NC}"
    exit 1
fi

NODE_VERSION=$(node -v)
NODE_VERSION=${NODE_VERSION#"v"}
NODE_VERSION_MAJOR=$(echo $NODE_VERSION | cut -d. -f1)
if [ $NODE_VERSION_MAJOR -lt 18 ]
then
    echo -e "${RED}Node version must be greater than v18, trying to fix with nvm...${NC}"

    echo -e "${BLUE}Upgrading Node version to v18 using nvm...${NC}"
    npm install -g n
    n 18
fi

echo -e -n "${BLUE}Enter your OpenAI API key (https://platform.openai.com/api-keys): ${NC}"
read OPENAI_API_KEY

if [ -z "$OPENAI_API_KEY" ]
then
    echo -e "${RED}OpenAI API key is required.${NC}"
    exit 1
fi

# echo -e -n "${BLUE}Enable telemetry to help us improve the product? (Y/n): ${NC}"
# read TELEMETRY -n 1
# echo    # move to a new line
# if [[ $TELEMETRY =~ ^[Nn]$ ]]
# then
#     echo -e "${YELLOW}Telemetry is disabled.${NC}\n"
# else
#     echo -e "${GREEN}Telemetry is enabled.${GREEN}\n"
# fi

# CURRENT_PATH=$(pwd)

# echo -e -n "${BLUE}Enter where to download Sweep ($CURRENT_PATH): ${NC}"
# read INSTALL_PATH

# if [ -z "$INSTALL_PATH" ]
# then
#     INSTALL_PATH=~/
# fi

INSTALL_PATH=$(pwd)

cd $INSTALL_PATH

if [ -d "sweep" ]; then
  echo "Sweep folder exists. Pulling latest changes..."
  cd sweep
  GIT_LFS_SKIP_SMUDGE=1 git fetch --depth 1
  git reset --hard @{u}
  cd platform
else
  echo -e "\n${BLUE}Cloning the Sweep repository in ${INSTALL_PATH}...${NC}\n"
  GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --single-branch https://github.com/sweepai/sweep
cd sweep/platform
fi

echo -e "\n${BLUE}Storing OpenAI API key...${NC}"
echo "OPENAI_API_KEY=$OPENAI_API_KEY\nNEXT_PUBLIC_DEFAULT_REPO_PATH=${pwd}\n" > .env.local
# if [[ $TELEMETRY =~ ^[Nn]$ ]]
# then
#     echo "NO_TELEMETRY=true" >> .env.local
# fi

echo -e "\n${BLUE}Installing Node dependencies...${NC}\n"
npm i

echo -e "\n${BLUE}Building the project...${NC}\n"
npm run build --no-lint

SHELL_CONFIG_FILE="$HOME/.zshrc"
SHELL_NAME=$(basename $SHELL)
if [[ $0 == */bash ]]; then
    SHELL_CONFIG_FILE=$HOME/.bashrc
elif [[ $0 == */zsh ]]; then
    SHELL_CONFIG_FILE=$HOME/.zshrc
fi

[[ "$INSTALL_PATH" != */ ]] && INSTALL_PATH="$INSTALL_PATH/"

echo -e "\n${BLUE}Setting alias for Sweep in ${SHELL_CONFIG_FILE}${NC}...\n"
echo "alias sweep='npm start --prefix ${INSTALL_PATH}sweep/platform'" >> $SHELL_CONFIG_FILE

echo -e "\n${GREEN}Setup complete!${NC}\n"

alias sweep="npm start --prefix ${INSTALL_PATH}sweep/platform"

echo -e "\n${YELLOW}To activate the sweep script, run:${NC}\n"
echo "exec $SHELL_NAME"

echo -e "\n${YELLOW}Then, to run the assistant, run:${NC}\n"
echo "npm start --prefix ${INSTALL_PATH}sweep/platform"
echo -e "\n${YELLOW}or${NC}\n"
echo "sweep"

send_event "assistant_install_success"
