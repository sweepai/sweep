"""
Proxy for the UI.
"""

import json
from typing import Any
import fastapi
from github import Github
import modal
from loguru import logger
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sweepai.app.config import SweepChatConfig
from sweepai.utils.config import SweepConfig
from sweepai.utils.constants import API_NAME, BOT_TOKEN_NAME, DB_NAME, PREFIX
from sweepai.utils.github_utils import get_github_client, get_installation_id
from sweepai.utils.event_logger import posthog
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, Function, Message, PullRequest, Snippet
from sweepai.core.sweep_bot import SweepBot
from sweepai.core.prompts import gradio_system_message_prompt, gradio_user_prompt

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
        "pymongo",
    )
)
secrets = [
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name("posthog"),
    modal.Secret.from_name("highlight")
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
            raise fastapi.HTTPException(status_code=403, detail="Sweep app is not installed on this repo. To install it, go to https://github.com/apps/sweep-ai")

        posthog.capture(request.github_username, "success", properties=metadata)

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
                    snippet.content = repo.get_contents(snippet.file_path, SweepConfig.get_branch(repo)).decoded_content.decode("utf-8")
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
            create_pr_func = modal.Function.lookup(API_NAME, "create_pr")
            system_message = gradio_system_message_prompt.format(
                snippets="\n".join([snippet.denotation + f"\n```{snippet.get_snippet()}```" for snippet in request.snippets]),
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
                    filename = item[0],
                    instructions = item[1],
                    change_type = "modify" if file_exists(item[0]) else "create", # TODO update this
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
    
...
240:        @app.post("/chat_stream")
241:        def chat_stream(request: ChatRequest):
242:            assert verify_config(request.config)
243:            metadata = {
244:                "function": "ui_chat_stream",
245:                "repo_full_name": request.config.repo_full_name,
246:                "organization": request.config.repo_full_name.split("/")[0],
247:                "username": request.config.github_username,
248:                "installation_id": request.config.installation_id,
249:                "mode": PREFIX,
250:            }
251:
252:            posthog.capture(request.config.github_username, "started", properties=metadata)
253:            try:
254:                messages = [Message.from_tuple(message) for message in request.messages]
255:                system_message = gradio_system_message_prompt.format(
256:                    snippets="\n".join([snippet.denotation + f"\n```{snippet.get_snippet()}```" for snippet in request.snippets]),
257:                    repo_name=request.config.repo_full_name,
258:                    repo_description="" # TODO: fill this
259:                )
260:                chatgpt = ChatGPT(messages=[Message(role="system", content=system_message, key="system")] + messages[:-1])
261:                if request.do_add_plan:
262:                    chatgpt.messages[-1].content += gradio_user_prompt
263:            except Exception as e:
264:                posthog.capture(request.config.github_username, "failed", properties={"error": str(e), **metadata})
265:                raise e
266:            def stream_chat():
267:                for chunk in chatgpt.chat_stream(messages[-1].content, model="gpt-4-0613", functions=request.functions, function_call=request.function_call):
268:                    yield json.dumps(chunk)
269:                posthog.capture(request.config.github_username, "success", properties=metadata)
270:            return StreamingResponse(
271:                stream_chat(),
272:                media_type="text/event-stream"
273:            )
274:        return app
275:
</new_file>

<new_file>
"""
Proxy for the UI.
"""

import json
from typing import Any
import fastapi
from github import Github
import modal
from loguru import logger
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sweepai.app.config import SweepChatConfig
from sweepai.utils.config import SweepConfig
from sweepai.utils.constants import API_NAME, BOT_TOKEN_NAME, DB_NAME, PREFIX
from sweepai.utils.github_utils import get_github_client, get_installation_id
from sweepai.utils.event_logger import posthog
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, Function, Message, PullRequest, Snippet
from sweepai.core.sweep_bot import SweepBot
from sweepai.core.prompts import gradio_system_message_prompt, gradio_user_prompt

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
        "pymongo",
    )
)
secrets = [
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name("posthog"),
    modal.Secret.from_name("highlight")
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
            raise fastapi.HTTPException(status_code=403, detail="Sweep app is not installed on this repo. To install it, go to https://github.com/apps/sweep-ai")

        posthog.capture(request.github_username, "success", properties=metadata)

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
...
127:    def generate_pull_request(self, retries=5) -> PullRequest:
128:        for count in range(retries):
129:            too_long = False
130:            try:
131:                logger.info(f"Generating for the {count}th time...")
132:                if too_long or count == retries - 2: # if on last try, use gpt4-32k (improved context window)
133:                    pr_text_response = self.chat(pull_request_prompt, message_key="pull_request")
134:                else:
135:                    pr_text_response = self.chat(pull_request_prompt, message_key="pull_request", model=SECONDARY_MODEL)
136:
137:                # Add triple quotes if not present
138:                if not pr_text_response.strip().endswith('"""'):
139:                    pr_text_response += '"""'
140:
141:                self.delete_messages_from_chat("pull_request")
142:            except Exception as e:
143:                e_str = str(e)
144:                if "too long" in e_str:
145:                    too_long = True
146:                logger.warning(f"Exception {e_str}. Failed to parse! Retrying...")
147:                self.delete_messages_from_chat("pull_request")
148:                continue
149:            pull_request = PullRequest.from_string(pr_text_response)
150:            pull_request.branch_name = "sweep/" + pull_request.branch_name[:250]
151:            return pull_request
152:        raise Exception("Could not generate PR text")
153:
154:
155:class GithubBot(BaseModel):
...
