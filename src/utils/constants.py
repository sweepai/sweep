"""
This file should be split into environment and config files
"""

PREFIX = "dev2"
DB_NAME = PREFIX + "-db"
API_NAME = PREFIX + "-api"
UTILS_NAME = PREFIX + "-utils"
SLACK_NAME = PREFIX + "-slack"
BOT_TOKEN_NAME = PREFIX + "-bot-token"
if PREFIX == "prod":
    BOT_TOKEN_NAME = "bot-token"
SWEEP_LOGIN = "sweep-ai[bot]"

if PREFIX == "prod":
    APP_ID = 307814
    ENV = PREFIX
elif PREFIX == "dev2":
    APP_ID = 327588
    ENV = PREFIX
    SWEEP_LOGIN = "sweep-canary[bot]"
elif PREFIX == "dev":
    APP_ID = 324098
    ENV = PREFIX
    SWEEP_LOGIN = "sweep-nightly[bot]"
LABEL_NAME = "sweep"
LABEL_COLOR = "#9400D3"
LABEL_DESCRIPTION = "Sweep your software chores"