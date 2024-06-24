import json
import os

from sweepai.agents.modify import modify
from sweepai.config.server import GITHUB_APP_ID, GITHUB_APP_PEM
from sweepai.core.entities import FileChangeRequest
from sweepai.dataclasses.code_suggestions import CodeSuggestion
from sweepai.utils.github_utils import ClonedRepo, get_installation_id
from sweepai.utils.github_utils import get_github_client


repo_full_name = os.environ["REPO_FULL_NAME"]
branch = os.environ["BRANCH"]
code_suggestions_path = os.environ.get("CODE_SUGGESTIONS_PATH", "code_suggestions.json")

org_name, repo = repo_full_name.split("/")
installation_id = get_installation_id(org_name, GITHUB_APP_PEM, GITHUB_APP_ID)
user_token, g = get_github_client(installation_id=installation_id)
cloned_repo = ClonedRepo(
    repo_full_name,
    installation_id=installation_id,
    token=user_token,
    branch=branch
)

file_change_requests = []

with open(code_suggestions_path, "r") as file:
    data = json.load(file)
    code_suggestions = [CodeSuggestion(**item) for item in data]

for code_suggestion in code_suggestions:
    change_type = "modify"
    if not code_suggestion.original_code:
        try:
            cloned_repo.get_file_contents(code_suggestion.file_path)
        except FileNotFoundError:
            change_type = "create"
    file_change_requests.append(
        FileChangeRequest(
            filename=code_suggestion.file_path,
            change_type=change_type,
            instructions=f"<original_code>\n{code_suggestion.original_code}\n</original_code>\n\n<new_code>\n{code_suggestion.new_code}\n</new_code>",
        ) 
    )

try:
    for stateful_code_suggestions in modify.stream(
        fcrs=file_change_requests,
        request="",
        cloned_repo=cloned_repo,
        relevant_filepaths=[code_suggestion.file_path for code_suggestion in code_suggestions],
    ):
        pass
except Exception as e:
    raise e