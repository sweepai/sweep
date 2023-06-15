"""
This file should be split into environment and config files
"""

PREFIX = "dev"
DB_NAME = PREFIX + "-db"
API_NAME = PREFIX + "-api"
SWEEP_LOGIN = "sweep-ai[bot]"

if PREFIX == "prod":
    APP_ID = 307814
    BOT_TOKEN_NAME = "bot-token"
    ENV = PREFIX
elif PREFIX == "dev2":
    APP_ID = 327588
    BOT_TOKEN_NAME = "dev2-bot-token"
    ENV = PREFIX
    SWEEP_LOGIN = "sweep-canary[bot]"
elif PREFIX == "dev":
    APP_ID = 324098
    BOT_TOKEN_NAME = "dev-bot-token"
    ENV = PREFIX
    SWEEP_LOGIN = "sweep-nightly[bot]"
LABEL_NAME = "sweep"
LABEL_COLOR = "#9400D3"
LABEL_DESCRIPTION = "Sweep your software chores"