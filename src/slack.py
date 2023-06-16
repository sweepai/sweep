import os

from fastapi import Request, Response
import modal
from pydantic import BaseModel

from src.utils.constants import BOT_TOKEN_NAME, DB_NAME, SLACK_NAME

image = modal.Image \
    .debian_slim() \
    .apt_install("git") \
    .pip_install(
        "slack-sdk", 
        "PyGithub",
        "gitpython",
        "loguru",
        "tqdm",
        "highlight-io",
        "posthog"
    )
stub = modal.Stub(SLACK_NAME)
secrets = [
    modal.Secret.from_name("slack"),
    modal.Secret.from_name(BOT_TOKEN_NAME),
]

installation_id = 37093089

class SlackSlashCommandRequest(BaseModel):
    channel_name: str
    text: str
    user_name: str
    user_id: str

@stub.function(
    image=image,
    secrets=secrets,
)
def reply_slack(request: SlackSlashCommandRequest):
    import slack_sdk
    from loguru import logger
    from src.core.entities import Snippet
    from src.utils.github_utils import get_github_client
    import src.utils.event_logger

    get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")
    client = slack_sdk.WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    thread = client.chat_postMessage(
        channel=f"#{request.channel_name}", 
        text=f">{request.text}\n- <@{request.user_name}>",
    )
    logger.info("Fetching relevant snippets...")
    repo_name = "sweepai/dummy-repo"
    snippets: list[Snippet] = get_relevant_snippets.call(
        repo_name, 
        query=request.text,
        n_results=5,
        installation_id=installation_id,
    )
    g = get_github_client(installation_id)
    repo = g.get_repo(repo_name)
    for snippet in snippets:
        snippet.content = repo.get_contents(snippet.file_path).decoded_content.decode("utf-8")
    message = "*Some relevant snippets I found:*\n\n"
    message += "\n".join(f"{snippet.get_slack_link(repo_name)}\n```{snippet.get_preview()}```" for snippet in snippets)
    response = client.chat_postMessage(
        channel=f"#{request.channel_name}",
        text=message,
        thread_ts=thread["ts"],
    )
    # logger.info(response)

@stub.function()
@modal.web_endpoint(method="POST")
async def entrypoint(request: Request):
    body = await request.form()
    print(body)
    request = SlackSlashCommandRequest(**dict(body))
    reply_slack.spawn(request)
    return Response(status_code=200)
