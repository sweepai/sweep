"""
Proxy for the UI.
"""

import json
import fastapi
from github import Github
import modal
from loguru import logger
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.app.config import SweepChatConfig

from src.core.chat import ChatGPT
from src.core.entities import FileChangeRequest, Function, Message, PullRequest, Snippet
from src.core.sweep_bot import SweepBot
from src.utils.constants import API_NAME, BOT_TOKEN_NAME, DB_NAME, PREFIX
from src.utils.github_utils import get_github_client, get_installation_id
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
        "config-path",
        "pyyaml",
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
    "keep_warm": 1
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
                                "description": "Concise NATURAL LANGUAGE summary of what to change in each file. There should be absolutely NO code.",
                                "example":  [
                                    "Refactor the algorithm by moving the main function to the top of the file.",
                                    "Change the implementation to recursion"
                                ]
                            },
                        },
                        "required": ["file_path", "instructions"]
                    },
                    "description": "A list of files to modify or create and corresponding instructions."
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
            },
            "required": ["plan", "title", "summary", "branch"]
        }
    ),
]

@stub.function(**FUNCTION_SETTINGS)
@modal.asgi_app(label=PREFIX + "-ui")
def _asgi_app():
    app = FastAPI()

    def verify_config(request: SweepChatConfig) -> bool:
        try:
            github_user_client = Github(request.github_pat)
            repo = github_user_client.get_repo(request.repo_full_name)
            assert repo
        except Exception as e:
            logger.warning(e)
            raise fastapi.HTTPException(status_code=403, detail="You do not have access to this repo")
        return True

    @app.post("/installation_id")
    def installation_id(request: SweepChatConfig) -> dict:
        # first check if user has access to the repo
        assert verify_config(request)

        try:
            organization, _repo_name = request.repo_full_name.split("/")
            installation_id = get_installation_id(organization)
            assert installation_id
        except Exception as e:
            logger.warning(e)
            raise fastapi.HTTPException(status_code=403, detail="Sweep app is not installed on this repo. To install it, go to https://github.com/apps/sweep-ai")

        return {"installation_id": installation_id}

    class SearchRequest(BaseModel):
        query: str
        config: SweepChatConfig
        n_results: int = 5

    @app.post("/search")
    def search(request: SearchRequest) -> list[Snippet]:
        logger.info("Searching for snippets...")
        get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")

        assert verify_config(request.config)

        snippets: list[Snippet] = get_relevant_snippets.call(
            request.config.repo_full_name,
            request.query,
            n_results=request.n_results,
            installation_id=request.config.installation_id
        )
        g = get_github_client(request.config.installation_id)
        repo = g.get_repo(request.config.repo_full_name)
        for snippet in snippets:
            try:
                snippet.content = repo.get_contents(snippet.file_path).decoded_content.decode("utf-8")
            except Exception:
                logger.error(snippet)
        return snippets

    class CreatePRRequest(BaseModel):
        # proposed PR information
        file_change_requests: list[tuple[str, str]]
        pull_request: PullRequest 

        # state information
        messages: list[tuple[str | None, str | None]]
        snippets: list[Snippet] = []

        config: SweepChatConfig
    
    @app.post("/create_pr")
    def create_pr(request: CreatePRRequest):
        assert verify_config(request.config)

        g = get_github_client(request.config.installation_id)
        repo = g.get_repo(request.config.repo_full_name)

        create_pr_func = modal.Function.lookup(API_NAME, "create_pr")
        system_message = gradio_system_message_prompt.format(
            snippets="\n".join([snippet.denotation + f"\n```{snippet.get_snippet()}```" for snippet in request.snippets]),
            repo_name=request.config.repo_full_name,
            repo_description="Sweep is an AI junior developer"
        )
        results = create_pr_func.call(
            [FileChangeRequest(
                filename = item[0],
                instructions = item[1],
                change_type = "create", # TODO update this
            ) for item in request.file_change_requests],
            request.pull_request,
            SweepBot(
                repo = repo,
                messages = [Message(role="system", content=system_message, key="system")] +
                    [Message.from_tuple(message) for message in request.messages],
            ),
            request.config.github_username,
            installation_id = request.config.installation_id,
            issue_number = None,
        )
        generated_pull_request = results["pull_request"]
        print(generated_pull_request)
        return {
            "html_url": generated_pull_request.html_url,
        }
    
    class ChatRequest(BaseModel):
        messages: list[tuple[str | None, str | None]]
        snippets: list[Snippet] = []
        config: SweepChatConfig

    @app.post("/chat")
    def chat(
        request: ChatRequest,
    ) -> str:
        assert verify_config(request.config)

        messages = [Message.from_tuple(message) for message in request.messages]
        chatgpt = ChatGPT(messages=messages[:-1])
        result = chatgpt.chat(messages[-1].content, model="gpt-4-0613")
        return result
    
    @app.post("/chat_stream")
    def chat_stream(request: ChatRequest):
        assert verify_config(request.config)

        messages = [Message.from_tuple(message) for message in request.messages]
        system_message = gradio_system_message_prompt.format(
            snippets="\n".join([snippet.denotation + f"\n```{snippet.get_snippet()}```" for snippet in request.snippets]),
            repo_name=request.config.repo_full_name,
            repo_description="" # TODO: fill this
        )
        chatgpt = ChatGPT(messages=[Message(role="system", content=system_message, key="system")] + messages[:-1])
        return StreamingResponse(
            (json.dumps(chunk) for chunk in chatgpt.chat_stream(messages[-1].content, model="gpt-4-0613", functions=functions, function_call={"name": "create_pr"})),
            media_type="text/event-stream"
        )
    return app
