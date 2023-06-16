import json
import os

from fastapi import Request, Response
import modal
from pydantic import BaseModel
from src.core.entities import Function

from src.utils.constants import BOT_TOKEN_NAME, DB_NAME, SLACK_NAME
from src.core.prompts import slack_slash_command_prompt

image = modal.Image \
    .debian_slim() \
    .apt_install("git") \
    .pip_install(
        "slack-sdk",
        "PyGithub",
        "gitpython",
        "openai",
        "anthropic",
        "loguru",
        "tqdm",
        "highlight-io",
        "posthog"
    )
stub = modal.Stub(SLACK_NAME)
secrets = [
    modal.Secret.from_name("slack"),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name(BOT_TOKEN_NAME),

]

functions = [
    Function(
        name="create_pr",
        description="Creates a PR.",
        parameters={
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of changes, files to add etc."
                },
            }
        }
    ),
    Function(
        name="get_relevant_snippets",
        description="Search engine for relevant snippets in the codebase in natural language.",
        parameters={
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search."
                }
            }
        }
    )
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
    from src.core.sweep_bot import SweepBot
    from src.core.entities import Snippet
    from src.utils.github_utils import get_github_client
    import src.utils.event_logger

    def populate_snippets(snippets: Snippet, repo):
        for snippet in snippets:
            snippet.content = repo.get_contents(snippet.file_path).decoded_content.decode("utf-8")

    get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")
    client = slack_sdk.WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    thread = client.chat_postMessage(
        channel=f"#{request.channel_name}", 
        text=f">{request.text}\n- <@{request.user_name}>",
    )
    logger.info("Fetching relevant snippets...")
    repo_name = "sweepai/dummy-repo"
    # snippets: list[Snippet] = get_relevant_snippets.call(
    #     repo_name, 
    #     query=request.text,
    #     n_results=5,
    #     installation_id=installation_id,
    # )
    snippets = [
        Snippet(start=0, end=2, file_path="app/test.py", content=""),
        Snippet(start=0, end=1, file_path="README.md", content=""),
        Snippet(start=0, end=11, file_path="HelloWorld.tsx", content=""),
    ]
    g = get_github_client(installation_id)
    repo = g.get_repo(repo_name)
    populate_snippets(snippets, repo)
    message = "*Some relevant snippets I found:*\n\n"
    message += "\n".join(f"{snippet.get_slack_link(repo_name)}\n```{snippet.get_preview()}```" for snippet in snippets)
    client.chat_postMessage(
        channel=f"#{request.channel_name}",
        text=message,
        thread_ts=thread["ts"],
    )
    prompt = slack_slash_command_prompt.format(
        relevant_snippets="\n".join([snippet.xml for snippet in snippets]),
        relevant_directories="\n".join([snippet.file_path for snippet in snippets]),
        repo_name=repo_name,
        repo_description=repo.description,
        username=request.user_name,
        query=request.text
    )
    print(prompt)
    sweep_bot = SweepBot(repo=repo)
    response = sweep_bot.chat(prompt, functions=functions)
    logger.info(response)

    while sweep_bot.messages[-1].role == "function":
        obj = json.loads(response)
        name = obj["name"]
        arguments = json.loads(obj["arguments"])
        if name == "get_relevant_snippets":
            logger.info("Searching for relevant snippets...")
            client.chat_postMessage(
                channel=f"#{request.channel_name}",
                text=f"I'm searching for more snippets with query \"{arguments['query']}\"...",
                thread_ts=thread["ts"],
            )
            additional_snippets: list[Snippet] = get_relevant_snippets.call(
                repo_name, 
                query=arguments["query"],
                n_results=5,
                installation_id=installation_id,
            )
            populate_snippets(additional_snippets, repo)
            # for snippet in snippets:
            #     snippet.content = repo.get_contents(snippet.file_path).decoded_content.decode("utf-8")
            additional_snippets_message = f"Found {len(additional_snippets)} additional snippets:\n\n" +  "\n".join(
                f"{snippet.get_slack_link(repo_name)}\n```{snippet.get_preview()}```" for snippet in additional_snippets
            )
            client.chat_postMessage(
                channel=f"#{request.channel_name}",
                text=additional_snippets_message,
                thread_ts=thread["ts"],
            )
            response = sweep_bot.chat(additional_snippets_message, functions=functions)
        elif name == "create_pr":
            client.chat_postMessage(
                channel=f"#{request.channel_name}",
                text=f"I'm creating a PR with {arguments['summary']}...",
                thread_ts=thread["ts"],
            )
            break
        else:
            raise Exception(f"Unknown function {name}")
    else:
        # no breaks were called
        client.chat_postMessage(
            channel=f"#{request.channel_name}",
            text=response,
            thread_ts=thread["ts"],
        )


@stub.function(image=image)
@modal.web_endpoint(method="POST")
async def entrypoint(request: Request):
    body = await request.form()
    print(body)
    request = SlackSlashCommandRequest(**dict(body))
    reply_slack.spawn(request)
    return Response(status_code=200)
