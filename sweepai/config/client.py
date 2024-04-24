from __future__ import annotations

import os
import traceback
from functools import lru_cache

import github
import yaml
from github.Repository import Repository
from loguru import logger
from pydantic import BaseModel

from sweepai.core.entities import EmptyRepository
from sweepai.utils.file_utils import read_file_with_fallback_encodings


class SweepConfig(BaseModel):
    include_dirs: list[str] = []
    exclude_dirs: list[str] = [
        ".git",
        "node_modules",
        "build",
        ".venv",
        "venv",
        "patch",
        "packages/blobs",
        "dist",
    ]
    exclude_path_dirs: list[str] = ["node_modules", "build", ".venv", "venv", ".git", "dist"]
    exclude_substrings_aggressive: list[str] = [ # aggressively filter out file paths, may drop some relevant files
        "integration",
        ".spec",
        ".test",
        ".json",
        "test"
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
        ".dfn",
        ".dfm",
        ".feature",
        "sweep.yaml",
        "pnpm-lock.yaml",
        "LICENSE",
        "poetry.lock",
    ]
    # cutoff for when we output truncated versions of strings, this is an arbitrary number and can be changed
    truncation_cutoff: int = 20000
    # Image formats
    max_file_limit: int = 60_000
    # github comments
    max_github_comment_body_length: int = 65535
    # allowed image types for vision
    allowed_image_types: list[str] = [
        "jpg",
        "jpeg",
        "webp",
        "png"
    ]

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
            except github.GithubException:
                # try a more robust branch test
                branch_name_parts = branch_name.split(" ")[0].split("/")
                branch_name_combos = []
                for i in range(len(branch_name_parts)):
                    branch_name_combos.append("/".join(branch_name_parts[i:]))
                try:
                    for i in range(len(branch_name_combos)):
                        branch_name = branch_name_combos[i]
                        try:
                            repo.get_branch(branch_name)
                            return branch_name
                        except Exception as e:
                            if i < len(branch_name_combos) - 1:
                                continue
                            else:
                                raise Exception(f"Branch not found: {e}")
                except Exception as e:
                    logger.exception(
                        f"Error when getting branch {branch_name}: {e}, traceback: {traceback.format_exc()}"
                    )
            except Exception as e:
                logger.exception(
                    f"Error when getting branch {branch_name}: {e}, traceback: {traceback.format_exc()}"
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
    
    # returns if file is excluded or not
    def is_file_excluded(self, file_path: str) -> bool:
        parts = file_path.split(os.path.sep)
        for part in parts:
            if part in self.exclude_dirs or part in self.exclude_exts:
                return True
        return False
    
    # returns if file is excluded or not, this version may drop actual relevant files
    def is_file_excluded_aggressive(self, dir: str, file_path: str) -> bool:
        # tiktoken_client = Tiktoken()
        # must exist
        if not os.path.exists(os.path.join(dir, file_path)) and not os.path.exists(file_path):
            return True
        full_path = os.path.join(dir, file_path)
        if os.stat(full_path).st_size > 240000 or os.stat(full_path).st_size < 5:
            return True
        # exclude binary 
        with open(full_path, "rb") as f:
            is_binary = False
            for block in iter(lambda: f.read(1024), b""):
                if b"\0" in block:
                    is_binary = True
                    break
            if is_binary:
                return True
        try:
            # fetch file
            data = read_file_with_fallback_encodings(full_path)
            lines = data.split("\n")
        except UnicodeDecodeError:
            logger.warning(f"UnicodeDecodeError in is_file_excluded_aggressive: {full_path}, skipping")
            return True
        line_count = len(lines)
        # if average line length is greater than 200, then it is likely not human readable
        if len(data)/line_count > 200:
            return True
    
        # check token density, if it is greater than 2, then it is likely not human readable
        # token_count = tiktoken_client.count(data)
        # if token_count == 0:
        #     return True
        # if len(data)/token_count < 2:
        #     return True
        
        # now check the file name
        parts = file_path.split(os.path.sep)
        for part in parts:
            if part in self.exclude_dirs or part in self.exclude_exts:
                return True
        for part in self.exclude_substrings_aggressive:
            if part in file_path:
                return True
        return False
        


@lru_cache(maxsize=None)
def get_gha_enabled(repo: Repository) -> bool:
    try:
        contents = repo.get_contents("sweep.yaml")
        gha_enabled = yaml.safe_load(contents.decoded_content.decode("utf-8")).get(
            "gha_enabled", False
        )
        return gha_enabled
    except SystemExit:
        raise SystemExit
    except Exception:
        logger.info(
            "Error when getting gha enabled, falling back to False"
        )
        return False


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
    except Exception:
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
    except Exception:
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
