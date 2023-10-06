import os
from typing import TypeVar

import yaml
from pydantic import BaseModel

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
    install: list[str] = ["trunk init"]
    check: list[str] = [
        "trunk fmt {file_path}",
        "trunk check --fix --print-failures {file_path}",
    ]

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
