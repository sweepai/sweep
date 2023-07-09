import os
from functools import lru_cache

import yaml
from github.Repository import Repository
from loguru import logger
from pydantic import BaseModel


class SweepConfig(BaseModel):
    include_dirs: list[str] = []
    exclude_dirs: list[str] = [".git", "node_modules", "venv"]
    include_exts: list[str] = ['.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs']
    exclude_exts: list[str] = ['.min.js', '.min.js.map', '.min.css', '.min.css.map']
    max_file_limit: int = 60_000

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.dict())

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "SweepConfig":
        data = yaml.safe_load(yaml_str)
        return cls.parse_obj(data)

    @staticmethod
    @lru_cache(maxsize=None)
    def get_branch(repo: Repository) -> str:
        default_branch = repo.default_branch
        try:
            contents = repo.get_contents(".github/sweep.yaml")
            branch_name = yaml.safe_load(contents.decoded_content.decode("utf-8"))["branch"]
            try:
                repo.get_branch(branch_name)
                return branch_name
            except Exception as e:
                logger.warning(f"Error when getting branch: {e}, creating branch")
                repo.create_git_ref(f"refs/heads/{branch_name}", repo.get_branch(default_branch).commit.sha)
                return branch_name
        except Exception as e:
            logger.warning(f"Error when getting branch: {e}, falling back to default branch")
            return default_branch

PREFIX = "dev"
ENV = PREFIX

DB_MODAL_INST_NAME = PREFIX + "-db"
API_MODAL_INST_NAME = PREFIX + "-api"
UTILS_MODAL_INST_NAME = PREFIX + "-utils"
SLACK_MODAL_INST_NAME = PREFIX + "-slack"


# goes under Modal 'github' secret name
GITHUB_BOT_TOKEN = os.environ.get('GITHUB_BOT_TOKEN')
GITHUB_APP_ID = os.environ.get('GITHUB_APP_ID')
GITHUB_BOT_USERNAME = os.environ.get('GITHUB_BOT_USERNAME')
GITHUB_LABEL_NAME = os.environ.get('GITHUB_LABEL_NAME', 'sweep')
GITHUB_LABEL_COLOR = os.environ.get('GITHUB_LABEL_COLOR')
GITHUB_LABEL_DESCRIPTION = os.environ.get('GITHUB_LABEL_DESCRIPTION')
GITHUB_APP_PEM = os.environ.get('GITHUB_APP_PEM')
GITHUB_CONFIG_BRANCH = os.environ.get('GITHUB_CONFIG_BRANCH', 'sweep-config')
GITHUB_DEFAULT_CONFIG = os.environ.get('GITHUB_DEFAULT_CONFIG', """# Reference: https://github.com/sweepai/sweep/blob/main/sweep.yaml
branch: "dev""")

# is set on clientside (optional)
GITHUB_APP_CLIENT_ID = os.environ.get('GITHUB_APP_CLIENT_ID', 'Iv1.91fd31586a926a9f')
SWEEP_API_ENDPOINT = os.environ.get('SWEEP_API_ENDPOINT', f"https://sweepai--{PREFIX}-ui.modal.run")

# goes under Modal 'openai-secret' secret name
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# goes under Modal 'huggingface' secret name
HUGGINGFACE_API_KEY = os.environ.get('HUGGINGFACE_API_KEY')
HUGGINGFACE_INFERENCE_URL = os.environ.get('HUGGINGFACE_INFERENCE_URL')

# goes under Modal 'slack' secret name
SLACK_CLIENT_ID = os.environ.get('SLACK_CLIENT_ID')
SLACK_CLIENT_SECRET = os.environ.get('SLACK_CLIENT_SECRET')
SLACK_APP_PAGE_URL = os.environ.get('SLACK_APP_PAGE_URL')
SLACK_APP_INSTALL_URL = os.environ.get('SLACK_APP_INSTALL_URL')

# goes under Modal 'anthropic' secret name
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# goes under Modal 'mongodb' secret name
MONGODB_URI = os.environ.get('MONGODB_URI')

# goes under Modal 'redis_url' secret name (optional)
REDIS_URL = os.environ.get('REDIS_URL')

# goes under Modal 'posthog' secret name (optional)
POSTHOG_API_KEY = os.environ.get('POSTHOG_API_KEY')

# goes under Modal 'highlight' secret name (optional)
HIGHLIGHT_API_KEY = os.environ.get('HIGHLIGHT_API_KEY')
