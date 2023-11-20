import os

from github import Github

from sweepai.agents.test_bot import TestBot
from sweepai.config.server import DEBUG, DEFAULT_GPT35_MODEL
from sweepai.core.entities import FileChangeRequest, Message, SweepContext
from sweepai.core.sweep_bot import SweepBot
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import ClonedRepo, get_token
from sweepai.utils.prompt_constructor import HumanMessagePrompt

DEBUG = True

installation_id = os.environ["INSTALLATION_ID"]
cloned_repo = ClonedRepo("sweepai/sweep", installation_id, "main")

additional_messages = [
    Message(
        role="user",
        content="""Repo: sweep: Sweep: AI-powered Junior Developer for small features and bug fixes.
Issue Title: Sweep: write unit tests for name_agent.py
Issue Description: ### Details

_No response_""",
        key="user",
    )
]
file_path = "sweepai/agents/name_agent.py"
request = "Write unit tests for name_agent.py"
changes_made = ""

repo = Github(get_token(installation_id=installation_id)).get_repo("sweepai/sweep")

sweep_bot = SweepBot.from_system_message_content(
    human_message=HumanMessagePrompt(
        repo_name="sweep",
        issue_url="",
        username="",
        title="Sweep: write unit tests for name_agent.py",
        summary="### Details\n\n_No response_",
        snippets=[],
        tree="",
        repo_description="",
        commit_history=[],
    ),
    repo=repo,
    chat_logger=None,
    model=DEFAULT_GPT35_MODEL,
    sweep_context=SweepContext(
        issue_url="",
        installation_id=installation_id,
        use_faster_model=False,
    ),
    cloned_repo=cloned_repo,
)

bot = TestBot(chat_logger=ChatLogger({"username": "kevinlu1248"}))
bot.model = "gpt-4-0613"
bot.write_test(
    file_change_request=FileChangeRequest(
        change_type="test",
        filename=file_path,
        instructions="Write unit tests for name_agent.py",
    ),
    additional_messages=additional_messages,
    file_path=file_path,
    request=request,
    changes_made=changes_made,
    cloned_repo=cloned_repo,
    check_sandbox=sweep_bot.check_sandbox,
)
