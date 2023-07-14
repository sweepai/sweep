"""
Proxy for the UI.
"""

from datetime import datetime
import json
from typing import Any

import fastapi
import modal
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from github import Github
from loguru import logger
from pydantic import BaseModel
from pymongo import MongoClient

from sweepai.app.config import SweepChatConfig
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, Function, Message, PullRequest, Snippet
from sweepai.core.prompts import gradio_system_message_prompt, gradio_user_prompt
from sweepai.core.sweep_bot import SweepBot
from sweepai.utils.config.client import SweepConfig
from sweepai.utils.config.server import MONGODB_URI, PREFIX, DB_MODAL_INST_NAME, API_MODAL_INST_NAME, BOT_TOKEN_NAME
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import get_github_client, get_installation_id

get_relevant_snippets = modal.Function.from_name(DB_MODAL_INST_NAME, "get_relevant_snippets")

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
        "pymongo",
    )
)
secrets = [
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("github"),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name("posthog"),
    modal.Secret.from_name("highlight"),
    modal.Secret.from_name("mongodb"),
]

FUNCTION_SETTINGS = {
    "image": image,
    "secrets": secrets,
    "timeout": 15 * 60,
    "keep_warm": 1
}


@stub.function(**FUNCTION_SETTINGS)
@modal.asgi_app(label=PREFIX + "-ui")
def _asgi_app():
    app = FastAPI()

    def verify_user(request: SweepChatConfig) -> bool:
        try:
            github_user_client = Github(request.github_pat)
            assert github_user_client.get_user().login == request.github_username
        except Exception as e:
            logger.warning(e)
            raise fastapi.HTTPException(status_code=403, detail="You do not have access to this repo")
        return True

    def verify_config(request: SweepChatConfig) -> bool:
        try:
            github_user_client = Github(request.github_pat)
            repo = github_user_client.get_repo(request.repo_full_name)
            assert repo
        except Exception as e:
            logger.warning(e)
            raise fastapi.HTTPException(status_code=403, detail="You do not have access to this repo")
        return True

    @app.post("/user_info")
    def user_info(request: SweepChatConfig) -> dict:
        assert verify_user(request)

        metadata = {
            "function": "ui_user_info",
            "repo_full_name": request.repo_full_name,
            "organization": (request.repo_full_name or "/").split("/")[0],
            "username": request.github_username,
            "installation_id": request.installation_id,
            "mode": PREFIX,
        }

        posthog.capture(request.github_username, "started", properties=metadata)

        current_month = datetime.utcnow().strftime('%m/%Y') 

        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, socketTimeoutMS=5000)
        db = client['llm']
        ticket_collection = db['tickets']
        user = ticket_collection.find_one({'username': request.github_username})
        is_paying_user = user.get('is_paying_user', False) if user else False

        result = ticket_collection.aggregate([
            {'$match': {'username': request.github_username}},
            {'$project': {current_month: 1, '_id': 0}}
        ])
        result_list = list(result)
        ticket_count = result_list[0].get(current_month, 0) if len(result_list) > 0 else 0
        logger.info(f'Ticket Count for {request.github_username} {ticket_count}')

        posthog.capture(request.github_username, "success", properties=metadata)

        return {
            "is_paying_user": is_paying_user,
            "remaining_tickets": max((60 if is_paying_user else 5) - ticket_count, 0),
        }

    @app.post("/installation_id")
    def installation_id(request: SweepChatConfig) -> dict:
        # first check if user has access to the repo
        assert verify_config(request)

        metadata = {
            "function": "ui_installation_id",
            "repo_full_name": request.repo_full_name,
            "organization": request.repo_full_name.split("/")[0],
            "username": request.github_username,
            "installation_id": request.installation_id,
            "mode": PREFIX,
        }

        posthog.capture(request.github_username, "started", properties=metadata)

        try:
            organization, _repo_name = request.repo_full_name.split("/")
            installation_id = get_installation_id(organization)
            assert installation_id
        except Exception as e:
            logger.warning(e)
            posthog.capture(request.github_username, "failed", properties={"error": str(e), **metadata})
            raise fastapi.HTTPException(status_code=403,
                                        detail="Sweep app is not installed on this repo. To install it, go to https://github.com/apps/sweep-ai")

        posthog.capture(request.github_username, "success", properties=metadata)

        return {"installation_id": installation_id}

    class SearchRequest(BaseModel):
        query: str
        config: SweepChatConfig
        n_results: int = 5

    @app.post("/search")
    def search(request: SearchRequest) -> list[Snippet]:
        logger.info("Searching for snippets...")
        get_relevant_snippets = modal.Function.lookup(DB_MODAL_INST_NAME, "get_relevant_snippets")

        assert verify_config(request.config)

        metadata = {
            "function": "ui_search",
            "repo_full_name": request.config.repo_full_name,
            "organization": request.config.repo_full_name.split("/")[0],
            "username": request.config.github_username,
            "installation_id": request.config.installation_id,
            "mode": PREFIX,
        }

        posthog.capture(request.config.github_username, "started", properties=metadata)

        try:
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
                    snippet.content = repo.get_contents(snippet.file_path,
                                                        SweepConfig.get_branch(repo)).decoded_content.decode("utf-8")
                except Exception:
                    logger.error(snippet)
        except Exception as e:
            posthog.capture(request.config.github_username, "failed", properties={"error": str(e), **metadata})
            raise e

        posthog.capture(request.config.github_username, "success", properties=metadata)
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

        metadata = {
            "function": "ui_create_pr",
            "repo_full_name": request.config.repo_full_name,
            "organization": request.config.repo_full_name.split("/")[0],
            "username": request.config.github_username,
            "installation_id": request.config.installation_id,
            "mode": PREFIX,
        }

        posthog.capture(request.config.github_username, "started", properties=metadata)

        try:
            create_pr_func = modal.Function.lookup(API_MODAL_INST_NAME, "create_pr")
            system_message = gradio_system_message_prompt.format(
                snippets="\n".join(
                    [snippet.denotation + f"\n```{snippet.get_snippet()}```" for snippet in request.snippets]),
                repo_name=request.config.repo_full_name,
                repo_description=repo.description
            )

            def file_exists(file_path: str) -> bool:
                try:
                    repo.get_contents(file_path, SweepConfig.get_branch(repo))
                    return True
                except Exception:
                    return False

            results = create_pr_func.call(
                [FileChangeRequest(
                    filename=item[0],
                    instructions=item[1],
                    change_type="modify" if file_exists(item[0]) else "create",  # TODO update this
                ) for item in request.file_change_requests],
                request.pull_request,
                SweepBot(
                    repo=repo,
                    messages=[Message(role="system", content=system_message, key="system")] +
                             [Message.from_tuple(message) for message in request.messages],
                ),
                request.config.github_username,
                installation_id=request.config.installation_id,
                issue_number=None,
            )
            generated_pull_request = results["pull_request"]
            print(generated_pull_request)
        except Exception as e:
            posthog.capture(request.config.github_username, "failed", properties={
                "error": str(e),
                **metadata
            })
            raise e

        posthog.capture(request.config.github_username, "success", properties=metadata)
        return {
            "html_url": generated_pull_request.html_url,
        }

    class ChatRequest(BaseModel):
        messages: list[tuple[str | None, str | None]]
        snippets: list[Snippet]
        config: SweepChatConfig
        do_add_plan: bool = False
        functions: list[Function] = []
        function_call: Any = "auto"

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
        metadata = {
            "function": "ui_chat_stream",
            "repo_full_name": request.config.repo_full_name,
            "organization": request.config.repo_full_name.split("/")[0],
            "username": request.config.github_username,
            "installation_id": request.config.installation_id,
            "mode": PREFIX,
        }

        posthog.capture(request.config.github_username, "started", properties=metadata)
        try:
            messages = [Message.from_tuple(message) for message in request.messages]
            system_message = gradio_system_message_prompt.format(
                snippets="\n".join(
                    [snippet.denotation + f"\n```{snippet.get_snippet()}```" for snippet in request.snippets]),
                repo_name=request.config.repo_full_name,
                repo_description=""  # TODO: fill this
            )
            chatgpt = ChatGPT(messages=[Message(role="system", content=system_message, key="system")] + messages[:-1])
            if request.do_add_plan:
                chatgpt.messages[-1].content += gradio_user_prompt
        except Exception as e:
            posthog.capture(request.config.github_username, "failed", properties={"error": str(e), **metadata})
            raise e

        def stream_chat():
            for chunk in chatgpt.chat_stream(messages[-1].content, model="gpt-4-0613", functions=request.functions,
                                             function_call=request.function_call):
                yield json.dumps(chunk)
            posthog.capture(request.config.github_username, "success", properties=metadata)

        return StreamingResponse(
            stream_chat(),
            media_type="text/event-stream"
        )

    return app
