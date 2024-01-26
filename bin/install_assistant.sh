#!/bin/bash

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

# echo -e "${GREEN}Welcome to Sweep AI Setup${NC}\n"
echo -e -n "${BLUE}Enter your OpenAI API key (https://platform.openai.com/api-keys): ${NC}"
read OPENAI_API_KEY

cd ~/
echo -e "\n${BLUE}Cloning the Sweep repository...${NC}\n"
# git clone https://github.com/sweepai/sweep
cd sweep/platform

echo -e "\n${BLUE}Storing OpenAI API key...${NC}\n"
# echo "OPENAI_API_KEY=$OPENAI_API_KEY" > .env.local

echo -e "\n${BLUE}Installing dependencies...${NC}\n"
# npm i

echo -e "\n${BLUE}Building the project...${NC}\n"
# npm run build

echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo -e "${YELLOW}To run the assistant, use:${NC}"
echo "npm start --prefix ~/sweep/platform"
echo ""

echo -e "${YELLOW}To create an alias, use:${NC}"
echo 'echo "alias sweep='npm start --prefix ~/sweep/platform'" >> ~/.zshrc'
