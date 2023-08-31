import os
from dotenv import load_dotenv
import base64

load_dotenv(dotenv_path=".env")

os.environ["GITHUB_APP_PEM"] = (
    os.environ.get(
        "GITHUB_APP_PEM",
        base64.b64decode(os.environ.get("GITHUB_APP_PEM_BASE64", "")).decode("utf-8"),
    )
    .replace("\\n", "\n")
    .strip('"')
)

os.environ["TRANSFORMERS_CACHE"] = os.environ.get(
    "TRANSFORMERS_CACHE", "cache/model"
)  # vector_db.py
os.environ["TIKTOKEN_CACHE_DIR"] = os.environ.get(
    "TIKTOKEN_CACHE_DIR", "cache/tiktoken"
)  # utils.py

SENTENCE_TRANSFORMERS_MODEL = os.environ.get(
    "SENTENCE_TRANSFORMERS_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",  # "all-mpnet-base-v2"
)

ENV = os.environ.get("ENV", "dev")
# ENV = os.environ.get("MODAL_ENVIRONMENT", "dev")

print(f"Using environment: {ENV}")
# ENV = PREFIX
# ENVIRONMENT = PREFIX

DB_MODAL_INST_NAME = "db"
DOCS_MODAL_INST_NAME = "docs"
API_MODAL_INST_NAME = "api"
UTILS_MODAL_INST_NAME = "utils"

BOT_TOKEN_NAME = "bot-token"

# goes under Modal 'discord' secret name (optional, can leave env var blank)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DISCORD_MEDIUM_PRIORITY_URL = os.environ.get("DISCORD_MEDIUM_PRIORITY_URL")
DISCORD_LOW_PRIORITY_URL = os.environ.get("DISCORD_LOW_PRIORITY_URL")

# goes under Modal 'github' secret name
GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID", os.environ.get("APP_ID"))
# deprecated: old logic transfer so upstream can use this
if GITHUB_APP_ID is None:
    if ENV == "main":
        GITHUB_APP_ID = "307814"
    elif ENV == "dev":
        GITHUB_APP_ID = "324098"
    elif ENV == "staging":
        GITHUB_APP_ID = "327588"
print("GitHub app ID:", GITHUB_APP_ID)
GITHUB_BOT_USERNAME = os.environ.get("GITHUB_BOT_USERNAME")

print(GITHUB_BOT_USERNAME)

# deprecated: left to support old logic
if not GITHUB_BOT_USERNAME:
    if ENV == "main":
        GITHUB_BOT_USERNAME = "sweep-ai[bot]"
    elif ENV == "dev":
        GITHUB_BOT_USERNAME = "sweep-nightly[bot]"
    elif ENV == "staging":
        GITHUB_BOT_USERNAME = "sweep-canary[bot]"
elif not GITHUB_BOT_USERNAME.endswith("[bot]"):
    GITHUB_BOT_USERNAME = GITHUB_BOT_USERNAME + "[bot]"

print(GITHUB_BOT_USERNAME)
print("TEST\n\n\n")

GITHUB_LABEL_NAME = os.environ.get("GITHUB_LABEL_NAME", "sweep")
GITHUB_LABEL_COLOR = os.environ.get("GITHUB_LABEL_COLOR", "9400D3")
GITHUB_LABEL_DESCRIPTION = os.environ.get(
    "GITHUB_LABEL_DESCRIPTION", "Sweep your software chores"
)
GITHUB_APP_PEM = os.environ.get("GITHUB_APP_PEM")
GITHUB_CONFIG_BRANCH = os.environ.get("GITHUB_CONFIG_BRANCH", "sweep/add-sweep-config")
GITHUB_DEFAULT_CONFIG = os.environ.get(
    "GITHUB_DEFAULT_CONFIG",
    """# Sweep AI turns bug fixes & feature requests into code changes (https://sweep.dev)
# For details on our config file, check out our docs at https://docs.sweep.dev

# If you use this be sure to frequently sync your default branch(main, master) to dev.
branch: '{branch}'
# By default Sweep will read the logs and outputs from your existing Github Actions. To disable this, set this to false.
gha_enabled: True
# This is the description of your project. It will be used by sweep when creating PRs. You can tell Sweep what's unique about your project, what frameworks you use, or anything else you want.
# Here's an example: sweepai/sweep is a python project. The main api endpoints are in sweepai/api.py. Write code that adheres to PEP8.
description: ''

# Default Values: https://github.com/sweepai/sweep/blob/main/sweep.yaml
""",
)


# goes under Modal 'openai-secret' secret name
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_DO_HAVE_32K_MODEL_ACCESS = (
    os.environ.get("OPENAI_DO_HAVE_32K_MODEL_ACCESS", "true").lower() == "true"
)

# goes under Modal 'anthropic' secret name (optional, can leave env var blank)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# goes under Modal 'mongodb' secret name
MONGODB_URI = os.environ.get("MONGODB_URI")

# goes under Modal 'redis_url' secret name (optional, can leave env var blank)
REDIS_URL = os.environ.get("REDIS_URL")
# deprecated: old logic transfer so upstream can use this
if not REDIS_URL:
    REDIS_URL = os.environ.get("redis_url")

ORG_ID = os.environ.get("ORG_ID")

# goes under Modal 'posthog' secret name (optional, can leave env var blank)
POSTHOG_API_KEY = os.environ.get(
    "POSTHOG_API_KEY", "phc_CnzwIB0W548wN4wEGeRuxXqidOlEUH2AcyV2sKTku8n"
)

E2B_API_KEY = os.environ.get("E2B_API_KEY")

SUPPORT_COUNTRY = os.environ.get("GDRP_LIST", "").split(",")

WHITELISTED_REPOS = os.environ.get("WHITELISTED_REPOS", "").split(",")

SECONDARY_MODEL = "gpt-3.5-turbo-16k-0613"

os.environ["TOKENIZERS_PARALLELISM"] = "false"
