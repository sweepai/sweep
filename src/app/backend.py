"""
Proxy for the UI.
"""

import json
import modal
from loguru import logger
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests
import httpx

from src.core.chat import ChatGPT
from src.core.entities import FileChangeRequest, Function, Message, PullRequest, Snippet
from src.core.sweep_bot import SweepBot
from src.utils.constants import API_NAME, BOT_TOKEN_NAME, DB_NAME, PREFIX
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

functions = [
    Function(
        name="create_pr",
        description="Creates a PR.",
        parameters={
            "properties": {
                "plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "The file path to change."
                            },
                            "instructions": {
                                "type": "string",
                                "description": "Detailed description of what the change as a list."
                            },
                        },
                        "required": ["file_path", "instructions"]
                    },
                    "description": "A list of files to modify or create and instructions for what to modify or create."
                },
                "title": {
                    "type": "string",
                    "description": "Title of PR",
                },
                "summary": {
                    "type": "string",
                    "description": "Detailed summary of PR",
                },
                "branch": {
                    "type": "string",
                    "description": "Name of branch to create PR in.",
                },
            }
        }
    ),
]

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

    class CreatePRRequest(BaseModel):
        file_change_requests: list[tuple[str, str]]
        pull_request: PullRequest
        messages: list[tuple[str | None, str | None]]
        repo: str
        username: str
        installation_id: int | None = None
    
    @app.post("/create_pr")
    def create_pr(request: CreatePRRequest):
        create_pr_func = modal.Function.lookup(API_NAME, "create_pr")
        system_message = gradio_system_message_prompt.format(
            snippets="\n".join([snippet.denotation + f"\n```{snippet.get_snippet()}```" for snippet in request.snippets]),
            repo_name="sweepai/sweep",
            repo_description="Sweep is an AI junior developer"
        )
        create_pr_func.call(
            [FileChangeRequest(
                filename = item[0],
                instructions = item[1],
                change_type =  "create", # TODO update this
            ) for item in request.file_change_request],
            request.pull_request,
            SweepBot(
                repo = request.repo,
                messages = [Message(role="system", content=system_message, key="system")] +
                    [Message.from_tuple(message) for message in request.messages],
            ),
            request.username,
            installation_id = request.installation_id,
            issue_number = None,
        )
        return {"status": "success"}
    
    class ChatRequest(BaseModel):
        messages: list[tuple[str | None, str | None]]
        snippets: list[Snippet] = []

    @app.post("/chat")
    def chat(
        request: ChatRequest,
    ) -> str:
        messages = [Message.from_tuple(message) for message in request.messages]
        chatgpt = ChatGPT(messages=messages[:-1])
        result = chatgpt.chat(messages[-1].content, model="gpt-3.5-turbo")
        return result
    
    @app.post("/chat_stream")
    def chat_stream(request: ChatRequest):
        messages = [Message.from_tuple(message) for message in request.messages]
        system_message = gradio_system_message_prompt.format(
            snippets="\n".join([snippet.denotation + f"\n```{snippet.get_snippet()}```" for snippet in request.snippets]),
            repo_name="sweepai/sweep",
            repo_description="Sweep is an AI junior developer"
        )
        chatgpt = ChatGPT(messages=[Message(role="system", content=system_message, key="system")] + messages[:-1])
        return StreamingResponse(
            (json.dumps(chunk) for chunk in chatgpt.chat_stream(messages[-1].content, model="gpt-3.5-turbo", functions=functions, function_call={"name": "create_pr"})),
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
        snippets: list[Snippet] = [],
        model: str = "gpt-4-0613",
    ) -> str:
        results = requests.post(
            self.api_endpoint + "/chat",
            json={
                "messages": messages,
                "snippets": [snippet.dict() for snippet in snippets],
            }
        )
        return results.json()
    
    def stream_chat(
        self, 
        messages: list[tuple[str | None, str | None]], 
        snippets: list[Snippet] = [],
        model: str = "gpt-4-0613"
    ):
        with httpx.Client(timeout=30) as client:
            with client.stream(
                'POST', 
                self.api_endpoint + '/chat_stream',
                json={
                    "messages": messages,
                    "snippets": [snippet.dict() for snippet in snippets],
                }
            ) as response:
                for delta_chunk in response.iter_text():
                    if not delta_chunk:
                        break
                    try:
                        yield json.loads(delta_chunk)
                    except json.decoder.JSONDecodeError as e: 
                        logger.error(delta_chunk)
                        raise e
