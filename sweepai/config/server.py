import base64
import os

from dotenv import load_dotenv
from loguru import logger

logger.print = logger.info

load_dotenv(dotenv_path=".env")

os.environ["GITHUB_APP_PEM"] = os.environ.get(
    "GITHUB_APP_PEM",
    base64.b64decode(os.environ.get("GITHUB_APP_PEM_BASE64", "")).decode("utf-8"),
)

if os.environ["GITHUB_APP_PEM"]:
    os.environ["GITHUB_APP_ID"] = (
        os.environ.get("GITHUB_APP_ID").replace("\\n", "\n").strip('"')
    )

os.environ["TRANSFORMERS_CACHE"] = os.environ.get(
    "TRANSFORMERS_CACHE", "/tmp/cache/model"
)  # vector_db.py
os.environ["TIKTOKEN_CACHE_DIR"] = os.environ.get(
    "TIKTOKEN_CACHE_DIR", "/tmp/cache/tiktoken"
)  # utils.py

SENTENCE_TRANSFORMERS_MODEL = os.environ.get(
    "SENTENCE_TRANSFORMERS_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",  # "all-mpnet-base-v2"
)
BATCH_SIZE = int(
    os.environ.get("BATCH_SIZE", 32)
)  # Tune this to 32 for sentence-transformers/all-MiniLM-L6-v2 on CPU

ENV = os.environ.get("ENV", "dev")
# ENV = os.environ.get("MODAL_ENVIRONMENT", "dev")

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
DISCORD_FEEDBACK_WEBHOOK_URL = os.environ.get("DISCORD_FEEDBACK_WEBHOOK_URL")

SWEEP_HEALTH_URL = os.environ.get("SWEEP_HEALTH_URL")
DISCORD_STATUS_WEBHOOK_URL = os.environ.get("DISCORD_STATUS_WEBHOOK_URL")

# goes under Modal 'github' secret name
GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID", os.environ.get("APP_ID"))
# deprecated: old logic transfer so upstream can use this
if GITHUB_APP_ID is None:
    if ENV == "prod":
        GITHUB_APP_ID = "307814"
    elif ENV == "dev":
        GITHUB_APP_ID = "324098"
    elif ENV == "staging":
        GITHUB_APP_ID = "327588"
GITHUB_BOT_USERNAME = os.environ.get("GITHUB_BOT_USERNAME")

# deprecated: left to support old logic
if not GITHUB_BOT_USERNAME:
    if ENV == "prod":
        GITHUB_BOT_USERNAME = "sweep-ai[bot]"
    elif ENV == "dev":
        GITHUB_BOT_USERNAME = "sweep-nightly[bot]"
    elif ENV == "staging":
        GITHUB_BOT_USERNAME = "sweep-canary[bot]"
elif not GITHUB_BOT_USERNAME.endswith("[bot]"):
    GITHUB_BOT_USERNAME = GITHUB_BOT_USERNAME + "[bot]"

GITHUB_LABEL_NAME = os.environ.get("GITHUB_LABEL_NAME", "sweep")
GITHUB_LABEL_COLOR = os.environ.get("GITHUB_LABEL_COLOR", "9400D3")
GITHUB_LABEL_DESCRIPTION = os.environ.get(
    "GITHUB_LABEL_DESCRIPTION", "Sweep your software chores"
)
GITHUB_APP_PEM = os.environ.get("GITHUB_APP_PEM")
GITHUB_APP_PEM = GITHUB_APP_PEM or os.environ.get("PRIVATE_KEY")
if GITHUB_APP_PEM is not None:
    GITHUB_APP_PEM = GITHUB_APP_PEM.strip(' \n"')  # Remove whitespace and quotes
    GITHUB_APP_PEM = GITHUB_APP_PEM.replace("\\n", "\n")

GITHUB_CONFIG_BRANCH = os.environ.get("GITHUB_CONFIG_BRANCH", "sweep/add-sweep-config")
GITHUB_DEFAULT_CONFIG = os.environ.get(
    "GITHUB_DEFAULT_CONFIG",
    """# Sweep AI turns bugs & feature requests into code changes (https://sweep.dev)
# For details on our config file, check out our docs at https://docs.sweep.dev/usage/config

# This setting contains a list of rules that Sweep will check for. If any of these rules are broken in a new commit, Sweep will create an pull request to fix the broken rule.
rules:
- "All docstrings and comments should be up to date."
{additional_rules}

# This is the branch that Sweep will develop from and make pull requests to. Most people use 'main' or 'master' but some users also use 'dev' or 'staging'.
branch: 'main'

# By default Sweep will read the logs and outputs from your existing Github Actions. To disable this, set this to false.
gha_enabled: True

# This is the description of your project. It will be used by sweep when creating PRs. You can tell Sweep what's unique about your project, what frameworks you use, or anything else you want.
#
# Example:
#
# description: sweepai/sweep is a python project. The main api endpoints are in sweepai/api.py. Write code that adheres to PEP8.
description: ''

# This sets whether to create pull requests as drafts. If this is set to True, then all pull requests will be created as drafts and GitHub Actions will not be triggered.
draft: False

# This is a list of directories that Sweep will not be able to edit.
blocked_dirs: []

# This is a list of documentation links that Sweep will use to help it understand your code. You can add links to documentation for any packages you use here.
#
# Example:
#
# docs:
#   - PyGitHub: ["https://pygithub.readthedocs.io/en/latest/", "We use pygithub to interact with the GitHub API"]
docs: []

# Sandbox executes commands in a sandboxed environment to validate code changes after every edit to guarantee pristine code. For more details, see the [Sandbox](./sandbox) page.
sandbox:
  install:
    - trunk init
  check:
    - trunk fmt {{file_path}}
    - trunk check --fix --print-failures {{file_path}}
""",
)


OPENAI_DO_HAVE_32K_MODEL_ACCESS = (
    os.environ.get("OPENAI_DO_HAVE_32K_MODEL_ACCESS", "true").lower() == "true"
)
OPENAI_USE_3_5_MODEL_ONLY = (
    os.environ.get("OPENAI_USE_3_5_MODEL_ONLY", "false").lower() == "true"
)

# goes under Modal 'anthropic' secret name (optional, can leave env var blank)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# goes under Modal 'mongodb' secret name
MONGODB_URI = os.environ.get("MONGODB_URI")

IS_SELF_HOSTED = MONGODB_URI is None

# goes under Modal 'redis_url' secret name (optional, can leave env var blank)
REDIS_URL = os.environ.get("REDIS_URL")
# deprecated: old logic transfer so upstream can use this
if not REDIS_URL:
    REDIS_URL = os.environ.get("redis_url", "redis://0.0.0.0:6379/0")

ORG_ID = os.environ.get("ORG_ID", None)
# goes under Modal 'posthog' secret name (optional, can leave env var blank)
POSTHOG_API_KEY = os.environ.get(
    "POSTHOG_API_KEY", "phc_CnzwIB0W548wN4wEGeRuxXqidOlEUH2AcyV2sKTku8n"
)

LOGTAIL_SOURCE_KEY = os.environ.get("LOGTAIL_SOURCE_KEY")

E2B_API_KEY = os.environ.get("E2B_API_KEY")

SUPPORT_COUNTRY = os.environ.get("GDRP_LIST", "").split(",")

WHITELISTED_REPOS = os.environ.get("WHITELISTED_REPOS", "").split(",")

SECONDARY_MODEL = "gpt-4-32k-0613"

os.environ["TOKENIZERS_PARALLELISM"] = "false"

ACTIVELOOP_TOKEN = os.environ.get("ACTIVELOOP_TOKEN", None)
SANDBOX_URL = os.environ.get("SANDBOX_URL", "http://0.0.0.0:8081")
if SANDBOX_URL is not None:
    logger.print(f"Using Sandbox URL: {SANDBOX_URL}")

HIGHLIGHT_API_KEY = os.environ.get("HIGHLIGHT_API_KEY", None)

VECTOR_EMBEDDING_SOURCE = os.environ.get(
    "VECTOR_EMBEDDING_SOURCE", "sentence-transformers"
)  # Alternate option is openai or huggingface and set the corresponding env vars

# Huggingface settings, only checked if VECTOR_EMBEDDING_SOURCE == "huggingface"
HUGGINGFACE_URL = os.environ.get("HUGGINGFACE_URL", None)
HUGGINGFACE_TOKEN = os.environ.get("HUGGINGFACE_TOKEN", None)

# Replicate settings, only checked if VECTOR_EMBEDDING_SOURCE == "replicate"
REPLICATE_API_KEY = os.environ.get("REPLICATE_API_KEY", None)
REPLICATE_URL = os.environ.get("REPLICATE_URL", None)
REPLICATE_DEPLOYMENT_URL = os.environ.get("REPLICATE_DEPLOYMENT_URL", None)

# Default OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)

# Azure settings, only checked if OPENAI_API_TYPE == "azure"
AZURE_API_KEY = os.environ.get("AZURE_API_KEY", None)
OPENAI_API_TYPE = os.environ.get("OPENAI_API_TYPE", None)
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", None)
OPENAI_API_VERSION = os.environ.get("OPENAI_API_VERSION", None)

OPENAI_API_ENGINE_GPT35 = os.environ.get("OPENAI_API_ENGINE_GPT35", None)
OPENAI_API_ENGINE_GPT4 = os.environ.get("OPENAI_API_ENGINE_GPT4", None)
OPENAI_API_ENGINE_GPT4_32K = os.environ.get("OPENAI_API_ENGINE_GPT4_32K", None)

WHITELISTED_USERS = os.environ.get("WHITELISTED_USERS", None)
if WHITELISTED_USERS:
    WHITELISTED_USERS = WHITELISTED_USERS.split(",")
    WHITELISTED_USERS.append(GITHUB_BOT_USERNAME)

DEBUG: bool = False
