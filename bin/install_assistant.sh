#!/bin/sh

RED="\033[0;31m"
GREEN="\033[1;32m"
BLUE="\033[1;34m"
YELLOW="\033[1;33m"
NC="\033[0m" # No Color

echo -e "
                   (@@@%%%%@@@&(.
             /%                  .*
           @           @@(    &,&
         ..            /  ,   *
         (             ,  /   @
         @@@@#         ( ..,@%
        @@@@@@@@@@@@@@@@ #@@@@.
       @@@@&@@@@&@@@@@@. @@@@@@#          ${GREEN}Sweep AI Assistant${NC}
       @@@  #@@#  %@@@@%@@@@@@@@@@@*
       (@@@@@@@@@@@@@@ @@@@@@@@@@@,       https://docs.sweep.dev/assistant
        %@@@@@@@@@@@@ /@@@@@@@@@@
          @@@@@@@@@,  ,@@@@@@@@
             ,@@&   @@@@@@@#
      @@@@@,        @
       @          # @
         #*      .. @
             %@,*% /
"

# Check if npm is installed
if ! command -v npm &> /dev/null
then
    echo -e "${RED}npm could not be found, please install npm and try again.${NC}"
    exit
fi

NODE_VERSION=$(node -v)
NODE_VERSION=${NODE_VERSION#"v"}
NODE_VERSION_MAJOR=$(echo $NODE_VERSION | cut -d. -f1)
if [ $NODE_VERSION_MAJOR -lt 18 ]
then
    echo -e "${RED}Node version must be greater than v18, trying to fix with nvm...${NC}"

    # Check if nvm is installed
    if ! command -v nvm &> /dev/null
    then
        echo -e "${RED}nvm could not be found, upgrade the Node version to v18 using nvm: ${BLUE}https://github.com/nvm-sh/nvm#installing-and-updating${NC}"
        exit
    else
        echo -e "${BLUE}Upgrading Node version to v18 using nvm...${NC}"
        nvm install 18
        nvm use 18
    fi
fi

echo -e -n "${BLUE}Enter your OpenAI API key (https://platform.openai.com/api-keys): ${NC}"
read OPENAI_API_KEY

if [ -z "$OPENAI_API_KEY" ]
then
    echo -e "${RED}OpenAI API key is required.${NC}"
    exit
fi

# CURRENT_PATH=$(pwd)

# echo -e -n "${BLUE}Enter where to download Sweep ($CURRENT_PATH): ${NC}"
# read INSTALL_PATH

# if [ -z "$INSTALL_PATH" ]
# then
#     INSTALL_PATH=~/
# fi

INSTALL_PATH=$(pwd)

cd $INSTALL_PATH
echo -e "\n${BLUE}Cloning the Sweep repository in ${INSTALL_PATH}...${NC}\n"
git clone https://github.com/sweepai/sweep
cd sweep/platform

echo -e "\n${BLUE}Storing OpenAI API key...${NC}"
echo "OPENAI_API_KEY=$OPENAI_API_KEY" > .env.local

echo -e "\n${BLUE}Installing Node dependencies...${NC}\n"
npm i

echo -e "\n${BLUE}Building the project...${NC}\n"
npm run build

[[ "$INSTALL_PATH" != */ ]] && INSTALL_PATH="$INSTALL_PATH/"

echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo -e "${YELLOW}To run the assistant, use:${NC}"
echo "npm start --prefix ${INSTALL_PATH}sweep/platform"
echo ""

SHELL_CONFIG_FILE="~/.zshrc"
if [[ $0 == */bash ]]; then
    SHELL_CONFIG_FILE=~/.bashrc
elif [[ $0 == */zsh ]]; then
    SHELL_CONFIG_FILE=~/.zshrc
fi

echo -e "${YELLOW}To create an alias, use:${NC}"
echo "echo \"alias sweep='npm start --prefix ${INSTALL_PATH}sweep/platform'\" >> ${SHELL_CONFIG_FILE}"
