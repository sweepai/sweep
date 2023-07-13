import json
import webbrowser
from typing import Any

import httpx
import requests
from loguru import logger
from pydantic import BaseModel

from sweepai.app.config import SweepChatConfig
from sweepai.core.entities import Function, PullRequest, Snippet
from sweepai.utils.config.client import GITHUB_APP_CLIENT_ID, SWEEP_API_ENDPOINT

create_pr_function = Function(
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
                            "description": "Concise NATURAL LANGUAGE summary of what to change in each file. There should be absolutely NO code, only English.",
                            "example": [
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
)

create_pr_function_call = {"name": "create_pr"}


def break_json(raw_json: str):
    # turns something like {"function_call": {"arguments": " \""}}{"function_call": {"arguments": "summary"}} into two objects
    try:
        yield json.loads(raw_json)
    except json.JSONDecodeError:
        for i in range(1, len(raw_json)):
            try:
                obj = json.loads(raw_json[:i])
                yield obj
                for item in break_json(raw_json[i:]):
                    yield item
                break
            except json.JSONDecodeError:
                pass


class APIClient(BaseModel):
    config: SweepChatConfig
    api_endpoint = SWEEP_API_ENDPOINT

    def __init__(self, config: SweepChatConfig):
        super().__init__(config=config)
        self.config = config
        logger.info(f"Initializing API client")
        logger.info(f"API endpoint: {self.api_endpoint}")
        logger.info(f"Github APP Client ID: {GITHUB_APP_CLIENT_ID}")

    def get_installation_id(self):
        results = requests.post(
            self.api_endpoint + "/installation_id",
            json=self.config.dict(),
        )
        if results.status_code == 401:
            print("Installation ID not found! Please install sweep first.")
            webbrowser.open_new_tab("https://github.com/apps/sweep-ai")
            raise Exception(results.json()["detail"])
        if results.status_code != 200:
            raise Exception(results.json()["detail"])
        obj = results.json()
        return obj["installation_id"]

    def search(
            self,
            query: str,
            n_results: int = 5,
    ):
        results = requests.post(
            self.api_endpoint + "/search",
            json={
                "query": query,
                "n_results": n_results,
                "config": self.config.dict(),
            }
        )
        if results.status_code != 200:
            raise Exception(results.text)
        snippets = [Snippet(**item) for item in results.json()]
        return snippets

    def create_pr(
            self,
            file_change_requests: list[tuple[str, str]],
            pull_request: PullRequest,
            messages: list[tuple[str | None, str | None]],
    ):
        results = requests.post(
            self.api_endpoint + "/create_pr",
            json={
                "file_change_requests": file_change_requests,
                "pull_request": pull_request,
                "messages": messages,
                "config": self.config.dict(),
            },
            timeout=10 * 60
        )
        try:
            return results.json()
        except json.JSONDecodeError:
            raise Exception(f"{results.text} is invalid JSON")

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
                "config": self.config.dict()
            }
        )
        try:
            return results.json()
        except json.JSONDecodeError:
            raise Exception(f"{results.text} is invalid JSON")

    def stream_chat(
            self,
            messages: list[tuple[str | None, str | None]],
            snippets: list[Snippet] = [],
            functions: list[Function] = [],
            function_call: Any = "auto",
            model: str = "gpt-4-0613"
    ):
        with httpx.Client(timeout=30) as client:  # sometimes this step is slow
            with client.stream(
                    'POST',
                    self.api_endpoint + '/chat_stream',
                    json={
                        "messages": messages,
                        "snippets": [snippet.dict() for snippet in snippets],
                        "do_add_plan": True,
                        "functions": [func.dict() for func in functions],
                        "function_call": function_call,
                        "config": self.config.dict()
                    }
            ) as response:
                for delta_chunk in response.iter_text():
                    if not delta_chunk:
                        break
                    try:
                        for item in break_json(delta_chunk):
                            yield item
                    except json.decoder.JSONDecodeError as e:
                        logger.error(delta_chunk)
                        raise e
