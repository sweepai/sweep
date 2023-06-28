"""
Proxy for the UI.
"""

import modal
from loguru import logger
from fastapi import FastAPI
from pydantic import BaseModel
import requests
from src.core.entities import Snippet

from src.utils.constants import BOT_TOKEN_NAME, DB_NAME, PREFIX
from src.utils.github_utils import get_github_client

# get_relevant_snippets = modal.Function.from_name(DB_NAME, "get_relevant_snippets")

stub = modal.Stub(PREFIX + "-ui")
image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install(
        "loguru",
        "tqdm",
        "posthog",
        "highlight-io",
        "PyGithub",
        "GitPython",
    )
)
secrets = [modal.Secret.from_name(BOT_TOKEN_NAME)]

FUNCTION_SETTINGS = {
    "image": image,
    "secrets": secrets,
    "timeout": 15 * 60,
}

@stub.function(**FUNCTION_SETTINGS)
@modal.asgi_app(label=PREFIX + "-ui")
def _asgi_app():
    app = FastAPI()

    @app.post("/search")
    def search(
        repo_name: str,
        query: str,
        n_results: int = 5,
        installation_id: int | None = None
    ):
        get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")
        snippets: list[Snippet] = get_relevant_snippets.call(
            repo_name,
            query,
            n_results=n_results,
            installation_id=installation_id
        )
        g = get_github_client(installation_id)
        repo = g.get_repo(repo_name)
        for snippet in snippets:
            try:
                snippet.content = repo.get_contents(snippet.file_path).decoded_content.decode("utf-8")
            except Exception:
                logger.error(snippet)
        return snippets
    
    @app.post("/chat")
    def chat(messages: list[tuple[str, str]]):
        pass

    return app

class APIClient(BaseModel):
    api_endpoint = f"https://sweepai--{PREFIX}-ui-dev.modal.run"

    def search(
        self,
        repo_name: str,
        query: str,
        n_results: int = 5,
        installation_id: int | None = None
    ):
        results = requests.post(
            self.api_endpoint + "/search",
            params={
                "repo_name": repo_name,
                "query": query,
                "n_results": n_results,
                "installation_id": installation_id,
            }
        )
        snippets = [Snippet(**item) for item in results.json()]
        return snippets
    