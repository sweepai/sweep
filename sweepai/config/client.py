from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict

import yaml
import requests
from github.Repository import Repository
from pydantic import BaseModel

from logn import logger
from sweepai.config.server import ENV
from sweepai.core.entities import EmptyRepository


class SweepConfig(BaseModel):
    include_dirs: list[str] = []
    exclude_dirs: list[str] = [
        ".git",
        "node_modules",
        "venv",
        "patch",
        "packages/blobs",
    ]
    include_exts: list[str] = [
        ".cs",
        ".csharp",
        ".py",
        ".md",
        ".txt",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
    ]
    exclude_exts: list[str] = [
        ".min.js",
        ".min.js.map",
        ".min.css",
        ".min.css.map",
        ".tfstate",
        ".tfstate.backup",
        ".jar",
        ".ipynb",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tiff",
        ".ico",
        ".mp3",
        ".wav",
        ".wma",
        ".ogg",
        ".flac",
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".patch",
        ".patch.disabled",
        ".wmv",
        ".m4a",
        ".m4v",
        ".3gp",
        ".3g2",
        ".rm",
        ".swf",
        ".flv",
        ".iso",
        ".bin",
        ".tar",
        ".zip",
        ".7z",
        ".gz",
        ".rar",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".svg",
        ".parquet",
        ".pyc",
        ".pub",
        ".pem",
    ]
    # Image formats
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
            except SystemExit:
                raise SystemExit
            except Exception:
                contents = repo.get_contents(".github/sweep.yaml")
            branch_name = yaml.safe_load(contents.decoded_content.decode("utf-8"))[
                "branch"
            ]
            try:
                repo.get_branch(branch_name)
                return branch_name
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.warning(f"Error when getting branch: {e}, creating branch")
                repo.create_git_ref(
                    f"refs/heads/{branch_name}",
                    repo.get_branch(default_branch).commit.sha,
                )
                return branch_name
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.info(
                f"Error when getting branch: {e}, falling back to default branch"
            )
            return default_branch

    @staticmethod
    def get_config(repo: Repository):
        try:
            contents = repo.get_contents("sweep.yaml")
            config = yaml.safe_load(contents.decoded_content.decode("utf-8"))
            return config
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.warning(f"Error when getting config: {e}, returning empty dict")
            if "This repository is empty." in str(e):
                raise EmptyRepository()
            return {}


@lru_cache(maxsize=None)
def get_gha_enabled(repo: Repository) -> bool:
    try:
        contents = repo.get_contents("sweep.yaml")
        gha_enabled = yaml.safe_load(contents.decoded_content.decode("utf-8")).get(
            "gha_enabled", True
        )
        return gha_enabled
    except SystemExit:
        raise SystemExit
    except Exception as e:
        try:
            contents = repo.get_contents(".github/sweep.yaml")
        except SystemExit:
            raise SystemExit
        except Exception as e:
            try:
                contents = repo.get_contents(".github/sweep.yaml")
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.warning(
                    f"Error when getting gha enabled: {e}, falling back to True"
                )
                return True
        gha_enabled = yaml.safe_load(contents.decoded_content.decode("utf-8")).get(
            "gha_enabled", True
        )
        return gha_enabled


@lru_cache(maxsize=None)
def get_description(repo: Repository) -> str:
    try:
        contents = repo.get_contents("sweep.yaml")
        description = yaml.safe_load(contents.decoded_content.decode("utf-8")).get(
            "description", ""
        )
        return description
    except SystemExit:
        raise SystemExit
    except Exception as e:
        return ""


@lru_cache(maxsize=None)
def get_sandbox_config(repo: Repository):
    try:
        contents = repo.get_contents("sweep.yaml")
        description = yaml.safe_load(contents.decoded_content.decode("utf-8")).get(
            "sandbox", {}
        )
        return description
    except SystemExit:
        raise SystemExit
    except Exception:
        return {}


@lru_cache(maxsize=None)
def get_branch_name_config(repo: Repository):
    try:
        contents = repo.get_contents("sweep.yaml")
        description = yaml.safe_load(contents.decoded_content.decode("utf-8")).get(
            "branch_use_underscores", False
        )
        return description
    except SystemExit:
        raise SystemExit
    except Exception:
        return False


@lru_cache(maxsize=None)
def get_documentation_dict(repo: Repository):
    try:
        sweep_yaml_content = repo.get_contents("sweep.yaml").decoded_content.decode(
            "utf-8"
        )
        sweep_yaml = yaml.safe_load(sweep_yaml_content)
        docs = sweep_yaml.get("docs", {})
        return docs
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.warning(f"Error when getting docs: {e}, returning empty dict")
        return {}


@lru_cache(maxsize=None)
def get_blocked_dirs(repo: Repository):
    try:
        sweep_yaml_content = repo.get_contents("sweep.yaml").decoded_content.decode(
            "utf-8"
        )
        sweep_yaml = yaml.safe_load(sweep_yaml_content)
        dirs = sweep_yaml.get("blocked_dirs", [])
        return dirs
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.warning(f"Error when getting docs: {e}, returning empty dict")
        return []


@lru_cache(maxsize=None)
def get_rules(repo: Repository):
    try:
        sweep_yaml_content = repo.get_contents("sweep.yaml").decoded_content.decode(
            "utf-8"
        )
        sweep_yaml = yaml.safe_load(sweep_yaml_content)
        rules = sweep_yaml.get("rules", [])
        return rules
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.warning(f"Error when getting rules: {e}, returning empty array")
        return []


# optional, can leave env var blank
GITHUB_APP_CLIENT_ID = os.environ.get("GITHUB_APP_CLIENT_ID", "Iv1.91fd31586a926a9f")

UPDATES_MESSAGE = """\
🎉 Latest improvements to Sweep:

* Getting Sweep to run linters before committing! Check out [Sweep Sandbox Configs](https://docs.sweep.dev/usage/config) to set it up.
* Added support for self-hosting! Check out [Self-hosting Sweep](https://docs.sweep.dev/deployment) to get started.

* [Self Hosting] Multiple options to compute vector embeddings, configure your .env file using [VECTOR_EMBEDDING_SOURCE](https://github.com/sweepai/sweep/blob/main/sweepai/config/server.py#L144)
"""
def send_feedback_to_discord(feedback):
    webhook_url = os.environ.get("DISCORD_FEEDBACK_WEBHOOK_URL")
    if webhook_url:
        data = {"content": feedback}
        response = requests.post(webhook_url, json=data)
        if response.status_code != 200:
            logger.warning(f"Failed to send feedback to discord: {response.content}")

RESTART_SWEEP_BUTTON = "↻ Restart Sweep"
SWEEP_GOOD_FEEDBACK = "👍 Sweep Did Well"
SWEEP_BAD_FEEDBACK = "👎 Sweep Needs Improvement"
