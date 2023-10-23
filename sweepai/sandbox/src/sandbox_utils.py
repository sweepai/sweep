import os
from typing import TypeVar

import yaml
from loguru import logger
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

files_to_install_scripts = {
    "package-lock.json": "npm i",
    "requirements.txt": "pip install -r requirements.txt",
    "poetry.lock": "poetry install",
    "setup.py": "pip install -e .",
    # "pyproject.toml": "poetry install",
    "yarn.lock": "yarn install",
    "pnpm-lock.yaml": "pnpm i",
    ".pre-commit-config.yaml": "pre-commit install",
}


class Sandbox(BaseModel):
    install: list[str] = ["trunk init"]
    check: list[str] = [
        "trunk fmt {file_path} || exit 0",
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

    @classmethod
    def from_directory(cls, path: str):
        if os.path.exists(os.path.join(path, "sweep.yaml")):
            sandbox = cls.from_yaml(open(os.path.join(path, "sweep.yaml")).read())
            is_default_sandbox = True
            if sandbox.install != ["trunk init"]:
                is_default_sandbox = False
            if not all(command.startswith("trunk") for command in sandbox.check):
                is_default_sandbox = False
            if not is_default_sandbox:
                return sandbox
        logger.info("Using default sandbox")
        sandbox = cls()
        for filename, script in files_to_install_scripts.items():
            if os.path.exists(os.path.join(path, filename)):
                logger.info(f"Found {filename} in repo, installing {script}")
                sandbox.install = [script] + sandbox.install
        ls = os.listdir(path)
        if "requirements.txt" in ls:
            sandbox.check.append(
                "if [[ $(echo \"{file_path}\" | grep 'test.*\.py$') ]]; then PYTHONPATH=. python {file_path}; else exit 0; fi"
            )
            contents = open(os.path.join(path, "requirements.txt")).read()
            if "pytest" in contents:
                sandbox.check.append(
                    'if [[ "{file_path}" == *test*.py ]]; then PYTHONPATH=. pytest {file_path}; else exit 0; fi'
                )
        # elif "pyproject.toml" in ls:
        #     sandbox.check.append(
        #         "if [[ $(echo \"{file_path}\" | grep 'test.*\.py$') ]]; then PYTHONPATH=. poetry run python {file_path}; else exit 0; fi"
        #     )
        #     contents = open(os.path.join(path, "pyproject.toml")).read()
        #     if "pytest" in contents:
        #         sandbox.check.append(
        #             'if [[ "{file_path}" == *test*.py ]]; then PYTHONPATH=. poetry run pytest {file_path}; else exit 0; fi'
        #         )
        return sandbox
