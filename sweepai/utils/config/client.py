from __future__ import annotations

import os
from functools import lru_cache

import yaml
from github.Repository import Repository
from loguru import logger
from pydantic import BaseModel
from sweepai.utils.config.server import PREFIX


class SweepConfig(BaseModel):
    include_dirs: list[str] = []
    exclude_dirs: list[str] = [".git", "node_modules", "venv"]
    include_exts: list[str] = ['.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs']
    exclude_exts: list[str] = ['.min.js', '.min.js.map', '.min.css', '.min.css.map', '.tfstate', '.tfstate.backup',
                               '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.ico', '.mp3', '.wav', '.wma', '.ogg',
                               '.flac', '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.m4a', '.m4v', '.3gp', '.3g2', '.rm',
                               '.swf', '.flv', '.iso', '.bin', '.tar', '.zip', '.7z', '.gz', '.rar', '.pdf', '.doc',
                               '.docx', '.xls', '.xlsx', '.ppt', '.pptx']
    ]  # Image formats
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
            try:
                contents = repo.get_contents("sweep.yaml")
            except Exception:
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


@staticmethod
@lru_cache(maxsize=None)
def get_gha_enabled(repo: Repository) -> bool:
    try:
        contents = repo.get_contents("sweep.yaml")
        gha_enabled = yaml.safe_load(contents.decoded_content.decode("utf-8")).get("gha_enabled", True)
        return gha_enabled
    except Exception as e:
        try:
            contents = repo.get_contents(".github/sweep.yaml")
        except Exception as e:
            try:
                contents = repo.get_contents(".github/sweep.yaml")
            except Exception as e:
                logger.warning(f"Error when getting gha enabled: {e}, falling back to True")
                return True
        gha_enabled = yaml.safe_load(contents.decoded_content.decode("utf-8")).get("gha_enabled", True)
        return gha_enabled

@staticmethod
@lru_cache(maxsize=None)
def get_description(repo: Repository) -> str:
    try:
        contents = repo.get_contents("sweep.yaml")
        description = yaml.safe_load(contents.decoded_content.decode("utf-8")).get("description", "")
        return description
    except Exception as e:
        return ""

# optional, can leave env var blank
GITHUB_APP_CLIENT_ID = os.environ.get('GITHUB_APP_CLIENT_ID', 'Iv1.91fd31586a926a9f')
SWEEP_API_ENDPOINT = os.environ.get('SWEEP_API_ENDPOINT', f"https://sweepai--{PREFIX}-ui.modal.run")
