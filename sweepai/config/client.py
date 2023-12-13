from __future__ import annotations

import os
import traceback
from functools import lru_cache
from exceptions import Exception

import yaml
from github.Repository import Repository
from loguru import logger
from pydantic import BaseModel

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
        ".download",
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
        ".ttf",
        "sweep.yaml",
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
    @lru_cache()
    def get_branch(repo: Repository, override_branch: str | None = None) -> str:
        if override_branch:
            branch_name = override_branch
            try:
                repo.get_branch(branch_name)
                return branch_name
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.exception(
                    f"Error when getting branch: {e}, traceback: {traceback.format_exc()}"
                )

        default_branch = repo.default_branch
        try:
            sweep_yaml_dict = {}
            try:
                contents = repo.get_contents("sweep.yaml")
                sweep_yaml_dict = yaml.safe_load(
                    contents.decoded_content.decode("utf-8")
                )
            except SystemExit:
                raise SystemExit
            if "branch" not in sweep_yaml_dict:
                return default_branch
            branch_name = sweep_yaml_dict["branch"]
            try:
                repo.get_branch(branch_name)
                return branch_name
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.exception(
                    f"Error when getting branch: {e}, traceback: {traceback.format_exc()}, creating branch"
                )
                repo.create_git_ref(
                    f"refs/heads/{branch_name}",
                    repo.get_branch(default_branch).commit.sha,
                )
                return branch_name
        except SystemExit:
            raise SystemExit
        except Exception:
            return default_branch

    @staticmethod
    def get_config(repo: Repository):
        try:
            contents = repo.get_contents("sweep.yaml")
            config = yaml.safe_load(contents.decoded_content.decode("utf-8"))
            return SweepConfig(**config)
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.warning(f"Error when getting config: {e}, returning empty dict")
            if "This repository is empty." in str(e):
                raise EmptyRepository()
            return SweepConfig()

    @staticmethod
    def get_draft(repo: Repository):
        try:
            contents = repo.get_contents("sweep.yaml")
            config = yaml.safe_load(contents.decoded_content.decode("utf-8"))
            return config.get("draft", False)
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.warning(f"Error when getting draft: {e}, returning False")
            return False


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
        logger.exception(
            f"Error when getting gha enabled: {e}, traceback: {traceback.format_exc()}, falling back to True"
        )
        return True


@lru_cache(maxsize=None)
def get_description(repo: Repository) -> dict:
    try:
        contents = repo.get_contents("sweep.yaml")
        sweep_yaml = yaml.safe_load(contents.decoded_content.decode("utf-8"))
        description = sweep_yaml.get("description", "")
        rules = sweep_yaml.get("rules", [])
        rules = "\n * ".join(rules[:3])
        return {"description": description, "rules": rules}
    except SystemExit:
        raise SystemExit
    except Exception:
        return {"description": "", "rules": ""}


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
        try:
            contents = repo.get_contents(".github/sweep.yaml")
        except Exception:
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
        try:
            sweep_yaml_content = repo.get_contents(".github/sweep.yaml").decoded_content.decode("utf-8")
        except Exception:
            sweep_yaml_content = repo.get_contents("sweep.yaml").decoded_content.decode("utf-8")
        sweep_yaml = yaml.safe_load(sweep_yaml_content)
        docs = sweep_yaml.get("docs", {})
        return docs
    except SystemExit:
        raise SystemExit
    except Exception:
        return {}


@lru_cache(maxsize=None)
def get_blocked_dirs(repo: Repository):
    try:
        try:
            sweep_yaml_content = repo.get_contents(".github/sweep.yaml").decoded_content.decode("utf-8")
        except Exception:
            sweep_yaml_content = repo.get_contents("sweep.yaml").decoded_content.decode("utf-8")
        sweep_yaml = yaml.safe_load(sweep_yaml_content)
        dirs = sweep_yaml.get("blocked_dirs", [])
        return dirs
    except SystemExit:
        raise SystemExit
    except Exception:
        return []


@lru_cache(maxsize=None)
def get_rules(repo: Repository):
    try:
        try:
            sweep_yaml_content = repo.get_contents(".github/sweep.yaml").decoded_content.decode("utf-8")
        except Exception:
            sweep_yaml_content = repo.get_contents("sweep.yaml").decoded_content.decode("utf-8")
        sweep_yaml = yaml.safe_load(sweep_yaml_content)
        rules = sweep_yaml.get("rules", [])
        return rules
    except SystemExit:
        raise SystemExit
    except Exception:
        return []


# optional, can leave env var blank
GITHUB_APP_CLIENT_ID = os.environ.get("GITHUB_APP_CLIENT_ID", "Iv1.91fd31586a926a9f")

RESTART_SWEEP_BUTTON = "↻ Restart Sweep"
SWEEP_GOOD_FEEDBACK = "👍 Sweep Did Well"
SWEEP_BAD_FEEDBACK = "👎 Sweep Needs Improvement"

RESET_FILE = "Rollback changes to "
REVERT_CHANGED_FILES_TITLE = "## Rollback Files For Sweep"

RULES_TITLE = (
    "## Apply [Sweep Rules](https://docs.sweep.dev/usage/config#rules) to your PR?"
)
RULES_LABEL = "**Apply:** "

DEFAULT_RULES = [
    "All new business logic should have corresponding unit tests.",
    "Refactor large functions to be more modular.",
    "Add docstrings to all functions and file headers.",
]

DEFAULT_RULES_STRING = """\
  - "All new business logic should have corresponding unit tests."
  - "Refactor large functions to be more modular."
  - "Add docstrings to all functions and file headers.\""""
