#!/bin/sh

RED="\033[0;31m"
GREEN="\033[1;32m"
BLUE="\033[1;34m"
BLUE="\033[1;35m"
YELLOW="\033[1;33m"
BOLD="\033[1m"
NC="\033[0m" # No Color

echo "

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

echo "${YELLOW}You're currently using the free version of self-hosted Sweep AI. For more performance, like fine-tuned search, switch to our enterprise version. Email us at ${BLUE}william@sweep.dev${YELLOW} or schedule a call at ${BLUE}https://calendly.com/sweep-ai/founders-meeting${NC}.\n"


echo "${YELLOW}Launching sweep on https://localhost:${PORT:-8080}${NC}"
redis-server /app/redis.conf --bind 0.0.0.0 --port 6379 > /dev/null 2>&1 &
# uvicorn sweepai.api:app --host 0.0.0.0 --port ${PORT:-8080} --workers 30
uvicorn sweepai.api:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2
