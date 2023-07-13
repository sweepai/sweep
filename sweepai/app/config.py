from __future__ import annotations

import os
import time
import webbrowser
from urllib.parse import parse_qs, unquote

import requests
import yaml
from config_path import ConfigPath
from pydantic import BaseModel

from sweepai.utils.config.client import GITHUB_APP_CLIENT_ID

DEVICE_CODE_ENDPOINT = "https://github.com/login/device/code"
USER_LOGIN_ENDPOINT = "https://github.com/login/device"
OAUTH_ACCESS_TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"

config_path = ConfigPath('sweep_chat', 'sweep', '.yaml')
CONFIG_FILE = config_path.saveFilePath()


class State(BaseModel):
    file_paths: list[str] = []
    chat_history: list[tuple[str | None, str | None]] = []
    snippets_text: str = "### Relevant Snippets:"
    plan: list[tuple[str, str]] = []


class SweepChatConfig(BaseModel):
    github_username: str
    github_pat: str  # secret
    repo_full_name: str | None = None
    installation_id: int | None = None
    state: State = State()
    version: str = "0.0.2"

    @classmethod
    def create(cls):
        device_code_response = requests.post(DEVICE_CODE_ENDPOINT, json={"client_id": GITHUB_APP_CLIENT_ID})
        parsed_device_code_response = parse_qs(unquote(device_code_response.text))
        print("\033[93m" + f"Open {USER_LOGIN_ENDPOINT} if it doesn't open automatically." + "\033[0m")
        print("\033[93m" + f"Paste the following code (copied to your clipboard) and click authorize:" + "\033[0m")
        print("\033[94m" + parsed_device_code_response["user_code"][0] + "\033[0m")  # prints in blue
        print("\033[93m" + "Once you've authorized, ** just wait a few seconds **..." + "\033[0m")  # prints in yellow
        time.sleep(3)
        webbrowser.open_new_tab(USER_LOGIN_ENDPOINT)
        for _ in range(10):
            time.sleep(5.5)
            try:
                oauth_access_token_response = requests.post(
                    OAUTH_ACCESS_TOKEN_ENDPOINT,
                    json={
                        "client_id": GITHUB_APP_CLIENT_ID,
                        "device_code": parsed_device_code_response["device_code"][0],
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    }
                )
                oauth_access_token_response = parse_qs(unquote(oauth_access_token_response.text))
                access_token = oauth_access_token_response["access_token"][0]
                assert access_token
                break
            except KeyError:
                pass
        else:
            raise Exception("Could not get access token")
        username_response = requests.get(
            "https://api.github.com/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
            }
        )

        print(
            "\033[92m" + f"Logged in successfully as {username_response.json()['login']}" + "\033[0m")  # prints in green

        return cls(
            github_username=username_response.json()["login"],
            github_pat=access_token
        )

    def save(self):
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(self.dict(), f)

    @staticmethod
    def is_initialized() -> bool:
        return os.path.exists(CONFIG_FILE)

    @classmethod
    def load(cls, recreate=False) -> SweepChatConfig:
        if recreate or not SweepChatConfig.is_initialized():
            config = cls.create()
            config.save()
            return config
        with open(CONFIG_FILE, "r") as f:
            return cls(**yaml.load(f, Loader=yaml.FullLoader))
