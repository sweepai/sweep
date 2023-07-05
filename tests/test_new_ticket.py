import os
import requests  # type: ignore
from loguru import logger

import modal

from sweepai.utils.config import GITHUB_BOT_TOKEN

stub = modal.Stub("tests")
image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install("openai", "PyGithub", "loguru")
)
secrets = [
    modal.Secret.from_name("github"),
    modal.Secret.from_name("openai-secret"),
]


@stub.function(image=image, secrets=secrets)
def test_new_ticket():
    owner = "sweepai"
    repo = "sweep"
    hook_id = "405082187"
    delivery_id = "110fcd50-c5ee-11ed-9c84-86c69c8a692f"
    access_token = os.environ["GITHUB_TOKEN"]
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {access_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    logger.info(
        f"https://api.github.com/repos/{owner}/{repo}/hooks/{hook_id}/deliveries/{delivery_id}/attempts"
    )
    results = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/hooks/{hook_id}/deliveries/{delivery_id}/attempts",
        headers=headers,
    )
    logger.info(results.status_code)
    logger.info(results.text)
