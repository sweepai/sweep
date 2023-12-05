# This is used to deploy the sandbox with screen
. ./venv/bin/activate
screen -S sandbox -X quit
git pull
. ./.env
screen -S sandbox -d -m ./start.sh
screen -ls
