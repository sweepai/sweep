import os

PREFIX = "prod"
ENV = PREFIX

DB_MODAL_INST_NAME = PREFIX + "-db"
API_MODAL_INST_NAME = PREFIX + "-api"
UTILS_MODAL_INST_NAME = PREFIX + "-utils"
SLACK_MODAL_INST_NAME = PREFIX + "-slack"

# deprecated: old logic transfer so upstream can use this; just create an empty modal secret for this
if PREFIX == "prod":
    BOT_TOKEN_NAME = "bot-token"
else:
    BOT_TOKEN_NAME = PREFIX + "-bot-token"

# goes under Modal 'discord' secret name (optional, can leave env var blank)
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

# goes under Modal 'github' secret name
GITHUB_BOT_TOKEN = os.environ.get('GITHUB_BOT_TOKEN')
# deprecated: old logic transfer so upstream can use this
if not GITHUB_BOT_TOKEN:
    GITHUB_BOT_TOKEN = os.environ.get('GITHUB_TOKEN')

GITHUB_APP_ID = os.environ.get('GITHUB_APP_ID')
# deprecated: old logic transfer so upstream can use this
if not GITHUB_APP_ID:
    if PREFIX == "prod":
        GITHUB_APP_ID = "307814"
    elif PREFIX == "dev":
        GITHUB_APP_ID = "324098"
    elif PREFIX == "dev2":
        GITHUB_APP_ID = "327588"
GITHUB_BOT_USERNAME = os.environ.get('GITHUB_BOT_USERNAME')
# deprecated: old logic transfer so upstream can use this
if not GITHUB_BOT_USERNAME:
    if PREFIX == "prod":
        GITHUB_BOT_USERNAME = "sweep-ai[bot]"
    elif PREFIX == "dev":
        GITHUB_BOT_USERNAME = "sweep-nightly[bot]"
    elif PREFIX == "dev2":
        GITHUB_BOT_USERNAME = "sweep-canary[bot]"

GITHUB_LABEL_NAME = os.environ.get('GITHUB_LABEL_NAME', 'sweep')
GITHUB_LABEL_COLOR = os.environ.get('GITHUB_LABEL_COLOR', '9400D3')
GITHUB_LABEL_DESCRIPTION = os.environ.get('GITHUB_LABEL_DESCRIPTION', 'Sweep your software chores')
GITHUB_APP_PEM = os.environ.get('GITHUB_APP_PEM')
GITHUB_CONFIG_BRANCH = os.environ.get('GITHUB_CONFIG_BRANCH', 'sweep/add-sweep-config')
GITHUB_DEFAULT_CONFIG = os.environ.get('GITHUB_DEFAULT_CONFIG', """# Sweep AI turns bug fixes & feature requests into code changes (https://sweep.dev)
# For details on our config file, check out our docs at https://docs.sweep.dev
# Reference: https://github.com/sweepai/sweep/blob/main/.github/sweep.yaml.

# If you use this be sure to frequently sync your default branch(main, master) to dev.
branch: '{branch}'
""")

# goes under Modal 'openai-secret' secret name
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_DO_HAVE_32K_MODEL_ACCESS = os.environ.get('OPENAI_DO_HAVE_32K_MODEL_ACCESS', 'true').lower() == 'true'

# goes under Modal 'slack' secret name
SLACK_CLIENT_ID = os.environ.get('SLACK_CLIENT_ID')
SLACK_CLIENT_SECRET = os.environ.get('SLACK_CLIENT_SECRET')
SLACK_APP_PAGE_URL = os.environ.get('SLACK_APP_PAGE_URL')
SLACK_APP_INSTALL_URL = os.environ.get('SLACK_APP_INSTALL_URL')

# goes under Modal 'anthropic' secret name
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# goes under Modal 'mongodb' secret name
MONGODB_URI = os.environ.get('MONGODB_URI')

# goes under Modal 'redis_url' secret name (optional, can leave env var blank)
REDIS_URL = os.environ.get('REDIS_URL')
# deprecated: old logic transfer so upstream can use this
if not REDIS_URL:
    REDIS_URL = os.environ.get('redis_url')

# goes under Modal 'posthog' secret name (optional, can leave env var blank)
POSTHOG_API_KEY = os.environ.get('POSTHOG_API_KEY')

# goes under Modal 'highlight' secret name (optional, can leave env var blank)
HIGHLIGHT_API_KEY = os.environ.get('HIGHLIGHT_API_KEY')

SECONDARY_MODEL = "gpt-3.5-turbo-16k-0613"
