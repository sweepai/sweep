"""
Proxy for the UI.
"""

import time
import modal
from loguru import logger
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests
import httpx

from src.core.chat import ChatGPT
from src.core.entities import Message, Snippet
from src.utils.constants import BOT_TOKEN_NAME, DB_NAME, PREFIX
from src.utils.github_utils import get_github_client
from src.core.prompts import gradio_system_message_prompt

get_relevant_snippets = modal.Function.from_name(DB_NAME, "get_relevant_snippets")

stub = modal.Stub(PREFIX + "-ui")
image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install(
        "loguru",
        "tqdm",
        "posthog",
        "openai",
        "anthropic",
        "highlight-io",
        "PyGithub",
        "GitPython",
    )
)
secrets = [
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("openai-secret")
]

FUNCTION_SETTINGS = {
    "image": image,
    "secrets": secrets,
    "timeout": 15 * 60,
}

@stub.function(**FUNCTION_SETTINGS)
@modal.asgi_app(label=PREFIX + "-ui")
def _asgi_app():
    app = FastAPI()

    class SearchRequest(BaseModel):
        repo_name: str
        query: str
        n_results: int = 5
        installation_id: int | None = None

    @app.post("/search")
    def search(request: SearchRequest) -> list[Snippet]:
        get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")
        snippets: list[Snippet] = get_relevant_snippets.call(
            request.repo_name,
            request.query,
            n_results=request.n_results,
            installation_id=request.installation_id
        )
        g = get_github_client(request.installation_id)
        repo = g.get_repo(request.repo_name)
        for snippet in snippets:
            try:
                snippet.content = repo.get_contents(snippet.file_path).decoded_content.decode("utf-8")
            except Exception:
                logger.error(snippet)
        return snippets
    
    class ChatRequest(BaseModel):
        messages: list[tuple[str | None, str | None]]

    @app.post("/chat")
    def chat(
        request: ChatRequest,
    ) -> str:
        messages = [Message.from_tuple(message) for message in request.messages]
        chatgpt = ChatGPT(messages=messages[:-1])
        result = chatgpt.chat(messages[-1].content, model="gpt-3.5-turbo")
        return result
    
    class StreamChatRequest(BaseModel):
        messages: list[tuple[str | None, str | None]]
    
    @app.post("/chat_stream")
    def chat_stream(request: StreamChatRequest):
        messages = [Message.from_tuple(message) for message in request.messages]
        chatgpt = ChatGPT(messages=[Message(role="system", content=gradio_system_message_prompt)] + messages[:-1])
        print(messages)
        return StreamingResponse(
            chatgpt.chat_stream(messages[-1].content, model="gpt-3.5-turbo"), 
            media_type="text/event-stream"
        )

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
            json={
                "repo_name": repo_name,
                "query": query,
                "n_results": n_results,
                "installation_id": installation_id,
            }
        )
        snippets = [Snippet(**item) for item in results.json()]
        return snippets
    
    def chat(
        self, 
        messages: list[tuple[str | None, str | None]],
        model: str = "gpt-4-0613",
    ) -> str:
        results = requests.post(
            self.api_endpoint + "/chat",
            json={
                "messages": messages,
            }
        )
        return results.json()
    
    def stream_chat(self, messages: list[tuple[str | None, str | None]], model: str = "gpt-4-0613"):
        with httpx.Client(timeout=30) as client:
            with client.stream(
                'POST', 
                self.api_endpoint + '/chat_stream',
                json={
                    "messages": messages
                }
            ) as response:
                for token in response.iter_text():
                    yield token
