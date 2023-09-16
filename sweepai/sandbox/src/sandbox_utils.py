import os

import yaml
from pydantic import BaseModel
from typing import Type, TypeVar, Any

Self = TypeVar("Self", bound="BaseModel")


REPO_PATH = "/home/user/repo"
GIT_PASS = (
    "cd ~; echo '#!/bin/sh\\necho \"{token}\"' > git-askpass.sh && chmod ugo+x"
    " git-askpass.sh"
)
GIT_CLONE = (
    "cd ~; export GIT_ASKPASS=./git-askpass.sh;"
    "git config --global credential.helper 'cache --timeout=3600';"
    "git clone https://{username}@github.com/{repo} " + REPO_PATH
)
GIT_BRANCH = f"cd {REPO_PATH}; " + "git checkout -B {branch}"
IMAGE_INSTALLATION = {
    "Nodejs": f"npm install",
}
PYTHON_CREATE_VENV = (
    f"cd {REPO_PATH} && python3 -m venv venv && source venv/bin/activate && poetry"
    " install"
)

LINT_CONFIG = """module.exports = {
    "env": {
        "browser": true,
        "es2021": true
    },
    "extends": [
        "eslint:recommended",
        "plugin:@typescript-eslint/recommended"
    ],
    "parser": "@typescript-eslint/parser",
    "parserOptions": {
        "ecmaVersion": "latest",
        "sourceType": "module",
        "ecmaFeatures": {
            "jsx": true
        }
    },
    "plugins": [
        "@typescript-eslint"
    ],
    "overrides": [
        {
            "env": {
                "node": true
            },
            "files": [
                ".eslintrc.{js,cjs}"
            ],
            "parserOptions": {
                "sourceType": "script"
            }
        }
    ],
    "rules": {
    }
}
"""


class Sandbox(BaseModel):
    # Make these multi-command
    # install_command: str = "trunk init"
    # linter_command: list[str] = ["trunk check {file_path}"]
    # format_command: str = "trunk fmt {file_path}"
    install: list[str] = ["trunk init"]
    check: list[str] = ["trunk fmt {file_path}", "trunk check --fix {file_path}"]

    @classmethod
    def from_yaml(cls, yaml_string: str):
        config = yaml.load(yaml_string, Loader=yaml.FullLoader)
        return cls(**config.get("sandbox", {}))

    @classmethod
    def from_config(cls, path: str = "sweep.yaml"):
        if os.path.exists(path):
            return cls.from_yaml(open(path).read())
        else:
            return cls()


# class Sandbox(BaseModel):
#     # Make these multi-command
#     install_command: str = None
#     format_command: str | list[str] = None
#     linter_command: str = None
#     repo: Any
#     repo_url: str = None

#     class Config:
#         arbitrary_types_allowed = True

#     @classmethod
#     def from_token(cls: Type[Self], repo, repo_url, config=None) -> Self | None:
#         config = config or get_sandbox_config(repo)
#         install_command = config.get("install", None)  # TODO: auto-detect
#         formatter = config.get("formatter", None)
#         linter = config.get("linter", None)

#         if install_command or formatter or linter:
#             logger.info(f"Using sandbox {install_command}, {formatter} and {linter}")
#         else:
#             logger.info("No sandbox config found")
#             return None

#         sandbox = cls(
#             install_command=install_command,
#             format_command=formatter,
#             linter_command=linter,
#             repo=repo,
#             repo_url=repo_url,
#         )

#         return sandbox
