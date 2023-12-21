import os
from urllib.parse import parse_qs

import modal
import requests
from fastapi import FastAPI
from github import Github
from loguru import logger
from pydantic import BaseModel

from sweepai.config.server import ENV
from sweepai.utils.event_logger import posthog

GITLAB_OAUTH_URL = "https://gitlab.com/oauth/token"

stub = modal.Stub(ENV + "-ext")
image = modal.Image.debian_slim().pip_install(
    "requests", "PyGithub", "loguru", "posthog"
)

FUNCTION_SETTINGS = {
    "image": image,
    "secrets": secrets,
    "timeout": 60 * 60,
    "keep_warm": 1,
}


@stub.function(**FUNCTION_SETTINGS)
@modal.asgi_app(label=ENV + "-ext")
def _asgi_app():
    asgi_app = FastAPI()

    class Config(BaseModel):
        username: str
        pat: str

    def validate_config(config: Config):
        headers = {'Authorization': f'Bearer {config.pat}'}
        response = requests.get('https://gitlab.example.com/api/v4/user', headers=headers)
        if response.status_code != 200:
            raise ValueError('Invalid PAT or unable to fetch user.')
        username = response.json().get('username')
        assert username == config.username
        return True

    @asgi_app.get("/oauth")
    def oauth(code: str):
        params = {
            "client_id": os.environ.get("GITLAB_CLIENT_ID"),
            "client_secret": os.environ.get("GITLAB_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": os.environ.get("GITLAB_REDIRECT_URI")
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(GITLAB_OAUTH_URL, data=params, headers=headers)
        if response.status_code > 400:
            return response.text
        else:
            access_token = response.json()['access_token']
            return {'access_token': access_token}

    @asgi_app.post("/auth")
    def auth(config: Config):
        assert validate_config(config)
        posthog.capture(
            "extension-installed",
            config.username,
            properties={"username": config.username},
        )
        return {"success": True}

    return asgi_app
