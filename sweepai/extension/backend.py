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

GITHUB_OAUTH_URL = "https://github.com/login/oauth/access_token"

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
        try:
            g = Github(config.pat)
        except Exception as e:
            logger.error(e)
            logger.error("Likely wrong correct.")
            raise e
        username = g.get_user().login
        assert username == config.username
        return True

    @asgi_app.get("/oauth")
    def oauth(code: str):
        # pass
        params = {
            "client_id": os.environ.get("GITHUB_CLIENT_ID"),
            "client_secret": os.environ.get("GITHUB_CLIENT_SECRET"),
            "code": code,
        }
        response = requests.post(GITHUB_OAUTH_URL, params=params)
        if response.status > 400:
            return response.text
        else:
            # parse response
            parsed = parse_qs(response.text)
            access_token = parsed.get("access_token")[0]
            return "Successfully authorized."

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
