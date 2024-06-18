import base64
import os

from dotenv import load_dotenv
from loguru import logger

logger.print = logger.info

load_dotenv(dotenv_path=".env", override=True, verbose=True)

os.environ["GITHUB_APP_PEM"] = os.environ.get("GITHUB_APP_PEM") or base64.b64decode(
    os.environ.get("GITHUB_APP_PEM_BASE64", "")
).decode("utf-8")

if os.environ["GITHUB_APP_PEM"]:
    os.environ["GITHUB_APP_ID"] = (
        (os.environ.get("GITHUB_APP_ID") or os.environ.get("APP_ID"))
        .replace("\\n", "\n")
        .strip('"')
    )

TEST_BOT_NAME = "sweep-nightly[bot]"
ENV = os.environ.get("ENV", "dev")

BOT_TOKEN_NAME = "bot-token"

GITHUB_BASE_URL = os.environ.get("GITHUB_BASE_URL", "https://api.github.com") # configure for enterprise

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
""",
)


MONGODB_URI = os.environ.get("MONGODB_URI", None)
IS_SELF_HOSTED = os.environ.get("IS_SELF_HOSTED", "true").lower() == "true"

REDIS_URL = os.environ.get("REDIS_URL")
if not REDIS_URL:
    REDIS_URL = os.environ.get("redis_url", "redis://0.0.0.0:6379/0")

ORG_ID = os.environ.get("ORG_ID", None)
POSTHOG_API_KEY = os.environ.get(
    "POSTHOG_API_KEY", "phc_CnzwIB0W548wN4wEGeRuxXqidOlEUH2AcyV2sKTku8n"
)

SUPPORT_COUNTRY = os.environ.get("GDRP_LIST", "").split(",")

WHITELISTED_REPOS = os.environ.get("WHITELISTED_REPOS", "").split(",")
BLACKLISTED_USERS = os.environ.get("BLACKLISTED_USERS", "").split(",")

# Default OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None) # this may be none, and it will use azure

OPENAI_API_TYPE = os.environ.get("OPENAI_API_TYPE", "anthropic")
assert OPENAI_API_TYPE in ["anthropic", "azure", "openai"], "Invalid OPENAI_API_TYPE"
OPENAI_EMBEDDINGS_API_TYPE = os.environ.get("OPENAI_EMBEDDINGS_API_TYPE", "openai")

AZURE_API_KEY = os.environ.get("AZURE_API_KEY", None)
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", None)
OPENAI_API_VERSION = os.environ.get("OPENAI_API_VERSION", None)
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", None)

OPENAI_EMBEDDINGS_API_TYPE = os.environ.get("OPENAI_EMBEDDINGS_API_TYPE", "openai")
OPENAI_EMBEDDINGS_AZURE_ENDPOINT = os.environ.get(
    "OPENAI_EMBEDDINGS_AZURE_ENDPOINT", None
)
OPENAI_EMBEDDINGS_AZURE_DEPLOYMENT = os.environ.get(
    "OPENAI_EMBEDDINGS_AZURE_DEPLOYMENT", None
)
OPENAI_EMBEDDINGS_AZURE_API_VERSION = os.environ.get(
    "OPENAI_EMBEDDINGS_AZURE_API_VERSION", None
)

OPENAI_API_ENGINE_GPT35 = os.environ.get("OPENAI_API_ENGINE_GPT35", None)
OPENAI_API_ENGINE_GPT4 = os.environ.get("OPENAI_API_ENGINE_GPT4", None)
MULTI_REGION_CONFIG = os.environ.get("MULTI_REGION_CONFIG", None)
if isinstance(MULTI_REGION_CONFIG, str):
    MULTI_REGION_CONFIG = MULTI_REGION_CONFIG.strip("'").replace("\\n", "\n")
    MULTI_REGION_CONFIG = [item.split(",") for item in MULTI_REGION_CONFIG.split("\n")]

WHITELISTED_USERS = os.environ.get("WHITELISTED_USERS", None)
if WHITELISTED_USERS:
    WHITELISTED_USERS = WHITELISTED_USERS.split(",")
    WHITELISTED_USERS.append(GITHUB_BOT_USERNAME)

DEFAULT_GPT4_MODEL = os.environ.get("DEFAULT_GPT4_MODEL", "gpt-4-0125-preview")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", None)
LOKI_URL = None

FILE_CACHE_DISABLED = os.environ.get("FILE_CACHE_DISABLED", "true").lower() == "true"
ENV = "prod" if GITHUB_BOT_USERNAME != TEST_BOT_NAME else "dev"

PROGRESS_BASE_URL = os.environ.get(
    "PROGRESS_BASE_URL", "https://progress.sweep.dev"
).rstrip("/")

DISABLED_REPOS = os.environ.get("DISABLED_REPOS", "").split(",")

GHA_AUTOFIX_ENABLED: bool = os.environ.get("GHA_AUTOFIX_ENABLED", False)
MERGE_CONFLICT_ENABLED: bool = os.environ.get("MERGE_CONFLICT_ENABLED", False)
INSTALLATION_ID = os.environ.get("INSTALLATION_ID", None)

AWS_ACCESS_KEY=os.environ.get("AWS_ACCESS_KEY")
AWS_SECRET_KEY=os.environ.get("AWS_SECRET_KEY")
AWS_REGION=os.environ.get("AWS_REGION")
ANTHROPIC_AVAILABLE = AWS_ACCESS_KEY and AWS_SECRET_KEY and AWS_REGION

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", None)

COHERE_API_KEY = os.environ.get("COHERE_API_KEY", None)

VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", None)

VOYAGE_API_AWS_ACCESS_KEY=os.environ.get("VOYAGE_API_AWS_ACCESS_KEY_ID")
VOYAGE_API_AWS_SECRET_KEY=os.environ.get("VOYAGE_API_AWS_SECRET_KEY")
VOYAGE_API_AWS_REGION=os.environ.get("VOYAGE_API_AWS_REGION")
VOYAGE_API_AWS_ENDPOINT_NAME=os.environ.get("VOYAGE_API_AWS_ENDPOINT_NAME", "voyage-code-2")

VOYAGE_API_USE_AWS = VOYAGE_API_AWS_ACCESS_KEY and VOYAGE_API_AWS_SECRET_KEY and VOYAGE_API_AWS_REGION

PAREA_API_KEY = os.environ.get("PAREA_API_KEY", None)

# TODO: we need to make this dynamic + backoff
BATCH_SIZE = int(
    os.environ.get("BATCH_SIZE", 64 if VOYAGE_API_KEY else 256) # Voyage only allows 128 items per batch and 120000 tokens per batch
)

DEPLOYMENT_GHA_ENABLED = os.environ.get("DEPLOYMENT_GHA_ENABLED", "true").lower() == "true"

JIRA_USER_NAME = os.environ.get("JIRA_USER_NAME", None)
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", None)
JIRA_URL = os.environ.get("JIRA_URL", None)

SLACK_API_KEY = os.environ.get("SLACK_API_KEY", None)

LICENSE_KEY = os.environ.get("LICENSE_KEY", None)
ALTERNATE_AWS = os.environ.get("ALTERNATE_AWS", "none").lower() == "true"

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", None)

SENTRY_URL = os.environ.get("SENTRY_URL", None)

CACHE_DIRECTORY = os.environ.get("CACHE_DIRECTORY", "/mnt/caches")

assert OPENAI_API_KEY, "OPENAI_API_KEY is required."
assert COHERE_API_KEY, "COHERE_API_KEY is required."

CIRCLE_CI_PAT = os.environ.get("CIRCLE_CI_PAT", None) # if this is present, we will poll from and get logs from circleci

DOCKER_ENABLED = os.environ.get("DOCKER_ENABLED", "false").lower() == "true"
DOCKERFILE_CONFIG_LOCATION = os.environ.get("DOCKERFILE_CONFIG_LOCATION", None) # location of the 