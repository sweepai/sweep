import json
import os

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

import modal
from pydantic import BaseModel
from pymongo import MongoClient
import requests
from sweepai.core.entities import FileChangeRequest, Function, PullRequest
import slack_sdk
from loguru import logger
from slack_sdk.oauth.installation_store import Installation, InstallationStore, Bot

from sweepai.core.sweep_bot import SweepBot
from sweepai.utils.github_utils import get_github_client
from sweepai.utils.constants import API_NAME, BOT_TOKEN_NAME, PREFIX, SLACK_NAME
from sweepai.core.prompts import slack_slash_command_prompt
from sweepai.utils.github_utils import get_installation_id
import sweepai.utils.event_logger

image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install(
        "slack-sdk",
        "slack-bolt",
        "pymongo",
        "PyGithub",
        "gitpython",
        "openai",
        "anthropic",
        "loguru",
        "tqdm",
        "highlight-io",
        "posthog",
        "pyyaml",
    )
)
stub = modal.Stub(SLACK_NAME)
secrets = [
    modal.Secret.from_name("slack"),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("mongodb"),
]

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
                                "description": "The file path to change.",
                            },
                            "instructions": {
                                "type": "string",
                                "description": "Detailed description of what the change as a list.",
                            },
                        },
                        "required": ["file_path", "instructions"],
                    },
                    "description": "A list of files to modify or create and instructions for what to modify or create.",
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
        },
    ),
    Function(
        name="get_relevant_snippets",
        description="Search engine for relevant snippets in the current repo in natural language.",
        parameters={
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search.",
                }
            }
        },
    ),
]

pr_format = """I'm going to create a PR with the following:

> *{title}*
> {summary}

I have the following plan:
{plan}

:hourglass_flowing_sand: Creating...
"""

pr_done_format = """:white_check_mark: Done creating PR at {url} with the following:
> *{title}*
> {summary}
"""

thread_query_format = "Message thread: {messages}"

# TODO(sweep): move to constants
slack_app_page = "https://sweepusers.slack.com/apps/A05D69L28HX-sweep"
slack_install_link = "https://slack.com/oauth/v2/authorize?client_id=5364586338420.5448326076609&scope=channels:read,chat:write,chat:write.public,commands,groups:read,im:read,incoming-webhook,mpim:read&user_scope="


class MongoDBInstallationStore(InstallationStore):
    def __init__(self):
        self.client = MongoClient(os.environ["MONGODB_URI"])
        self.db = self.client["slack"]
        self.installation_collection = self.db["installation"]
        self.bot_collection = self.db["bot"]

    def save(self, installation: Installation):
        self.installation_collection.replace_one(
            {
                "user_id": installation.user_id,
                "team_id": installation.team_id,
                "enterprise_id": installation.enterprise_id,
                "is_enterprise_install": installation.is_enterprise_install,
            },
            {
                "installation": installation.to_dict(),
                "user_id": installation.user_id,
                "team_id": installation.team_id,
                "enterprise_id": installation.enterprise_id,
                "is_enterprise_install": installation.is_enterprise_install,
                "prefix": PREFIX,
                "access_token": installation.bot_token,
            },
            upsert=True,
        )

    def save_bot(self, bot: Bot):
        self.bot_collection.replace_one(
            {
                "team_id": bot.team_id,
                "enterprise_id": bot.enterprise_id,
                "is_enterprise_install": bot.is_enterprise_install,
            },
            {
                "installation": bot.to_dict(),
                "team_id": bot.team_id,
                "enterprise_id": bot.enterprise_id,
                "is_enterprise_install": bot.is_enterprise_install,
                "prefix": PREFIX,
                "access_token": bot.bot_token,
            },
            upsert=True,
        )

    def find_installation(
        self,
        *,
        enterprise_id: str,
        team_id: str,
        is_enterprise_install: bool,
        user_id: str | None = None,
    ):
        if user_id:
            return Installation(
                **self.installation_collection.find_one(
                    {
                        "user_id": user_id,
                        "team_id": team_id,
                        "enterprise_id": enterprise_id,
                        "is_enterprise_install": is_enterprise_install,
                    }
                )["installation"]
            )
        else:
            return Installation(
                **self.installation_collection.find_one(
                    {
                        "team_id": team_id,
                        "enterprise_id": enterprise_id,
                        "is_enterprise_install": is_enterprise_install,
                    }
                )["installation"]
            )

    def find_bot(self, *enterprise_id: str, team_id: str, is_enterprise_install: bool):
        return Installation(
            **self.bot_collection.find_one(
                {
                    "enterprise_id": enterprise_id,
                    "team_id": team_id,
                    "is_enterprise_install": is_enterprise_install,
                }
            )["installation"]
        )

    def delete_installation(self, *, enterprise_id: str, team_id: str):
        self.installation_collection.delete_one(
            {
                "enterprise_id": enterprise_id,
                "team_id": team_id,
            }
        )

    def delete_bot(self, *, enterprise_id: str, team_id: str, user_id: str):
        self.installation_collection.delete_one(
            {"enterprise_id": enterprise_id, "team_id": team_id, "user_id": user_id}
        )


class SlackSlashCommandRequest(BaseModel):
    channel_name: str
    channel_id: str
    text: str
    user_name: str
    user_id: str
    team_id: str
    is_enterprise_install: bool
    enterprise_id: str | None = None


@stub.function(
    image=image,
    secrets=secrets,
    timeout=15 * 60,
)
def reply_slack(request: SlackSlashCommandRequest, thread_ts: str | None = None):
    try:
        create_pr = modal.Function.lookup(API_NAME, "create_pr")
        client = None
        installation_store = MongoDBInstallationStore()
        token = installation_store.find_installation(
            team_id=request.team_id,
            enterprise_id=request.enterprise_id,
            user_id=request.user_id,
            is_enterprise_install=request.is_enterprise_install,
        ).bot_token
        client = slack_sdk.WebClient(token=token)
    except Exception as e:
        logger.error(f"Error initializing Slack client: {e}")
        raise e

    try:
        channel_info = client.conversations_info(channel=request.channel_id)
        channel_description: str = channel_info["channel"]["purpose"]["value"]
        logger.info(f"Channel description: {channel_description}")

        repo_full_name = channel_description.split()[-1]
        logger.info(f"Repo name: {repo_full_name}")

        organization_name, repo_name = repo_full_name.split("/")

        try:
            installation_id = get_installation_id(organization_name)
            g = get_github_client(installation_id)
            repo = g.get_repo(repo_full_name)
        except Exception as e:
            # TODO: provide better instructions for installation
            client.chat_postMessage(
                channel=request.channel_id,
                text=f"An error has occurred with fetching the credentials for {repo_full_name}. Please ensure that the app is installed on the Github repo.",
            )
            raise e

        sweep_bot = SweepBot(repo=repo)

        search_already_done = bool(thread_ts)
        if not thread_ts:
            thread = client.chat_postMessage(
                channel=request.channel_id,
                text=f">{request.text}\n- <@{request.user_name}>",
            )
            thread_ts = thread["ts"]
            query = request.text
        else:
            messages = client.conversations_replies(
                channel=request.channel_id,
                ts=thread_ts,
            )["messages"]
            query = thread_query_format.format(
                messages="\n".join(
                    [
                        f"<message user={message['user']}>\n{message['text']}\n</message>"
                        for message in messages
                    ]
                )
            )
    except Exception as e:
        client.chat_postMessage(
            channel=request.channel_id,
            text=":exclamation: Sorry, something went wrong. Sometimes this is because the Github app is not installed on your repo.",
        )
        raise e

    try:
        if not search_already_done:
            logger.info("Fetching relevant snippets...")
            searching_message = client.chat_postMessage(
                channel=request.channel_id,
                text=":mag_right: Searching for relevant snippets...",
                thread_ts=thread_ts,
            )
            snippets = sweep_bot.search_snippets(
                request.text, installation_id=installation_id
            )
            message = ":mag_right: Some relevant snippets I found:\n\n"
            message += "\n".join(
                f"{snippet.get_slack_link(repo_name)}\n```{snippet.get_preview()}```"
                for snippet in snippets
            )
            client.chat_update(
                channel=request.channel_id,
                ts=searching_message["ts"],
                text=message,
            )
        else:
            snippets = []
        prompt = slack_slash_command_prompt.format(
            relevant_snippets="\n".join([snippet.xml for snippet in snippets]),
            relevant_directories="\n".join([snippet.file_path for snippet in snippets]),
            repo_name=repo_name,
            repo_description=repo.description,
            username=request.user_name,
            query=query,
        )
        response = sweep_bot.chat(
            prompt, functions=functions, function_name={"name": "create_pr"}
        )
        logger.info(response)

        while sweep_bot.messages[-1].function_call is not None:
            obj = sweep_bot.messages[-1].function_call
            name = obj["name"]
            arguments = json.loads(obj["arguments"])
            if name == "get_relevant_snippets":
                logger.info("Searching for relevant snippets...")
                search_message = client.chat_postMessage(
                    channel=request.channel_id,
                    text=f":mag_right: Searching \"{arguments['query']}\" in the codebase...",
                    thread_ts=thread_ts,
                )
                additional_snippets = sweep_bot.search_snippets(
                    arguments["query"], installation_id=installation_id
                )
                # additional_snippets = default_snippets
                additional_snippets_message = (
                    f":mag_right: Found {len(additional_snippets)} additional snippets with the query \"{arguments['query']}\":\n\n"
                    + "\n".join(
                        f"{snippet.get_slack_link(repo_name)}\n```{snippet.get_preview()}```"
                        for snippet in additional_snippets
                    )
                )
                client.chat_update(
                    channel=request.channel_id,
                    text=additional_snippets_message,
                    ts=search_message["ts"],
                )
                response = sweep_bot.chat(
                    additional_snippets_message, functions=functions
                )
            elif name == "create_pr":
                title = arguments["title"]
                summary = arguments["summary"]
                branch = arguments["branch"]
                plan = arguments["plan"]
                plan_message = "\n".join(
                    f"• `{file['file_path']}`: {file['instructions']}" for file in plan
                )
                plan_message = ">" + plan_message.replace("\n", "\n> ")

                creating_pr_message = client.chat_postMessage(
                    channel=request.channel_id,
                    text=pr_format.format(
                        title=title, summary=summary, plan=plan_message
                    ),
                    thread_ts=thread_ts,
                )
                file_change_requests = []
                for file in plan:
                    change_type = "create"
                    try:
                        contents = repo.get_contents(file["file_path"])
                        if contents:
                            change_type = "modify"
                    except:
                        pass
                    file_change_requests.append(
                        FileChangeRequest(
                            filename=file["file_path"],
                            instructions=file["instructions"],
                            change_type=change_type,
                        )
                    )
                pull_request = PullRequest(
                    title=title,
                    branch_name=branch,
                    content=summary,
                )
                results = create_pr.call(
                    file_change_requests=file_change_requests,
                    pull_request=pull_request,
                    sweep_bot=sweep_bot,
                    username=request.user_name,
                    installation_id=installation_id,
                )
                logger.debug(results)
                pr = results["pull_request"]
                client.chat_update(
                    channel=request.channel_id,
                    text=pr_done_format.format(
                        url=pr.html_url,
                        title=title,
                        summary=summary,
                    ),
                    ts=creating_pr_message["ts"],
                )
                break
            else:
                raise Exception(f"Unknown function {name}")
        else:
            # no breaks were called
            client.chat_postMessage(
                channel=request.channel_id, text=response, thread_ts=thread_ts
            )
    except Exception as e:
        client.chat_postMessage(
            channel=request.channel_id,
            text=":exclamation: Sorry, something went wrong.",
            thread_ts=thread_ts,
        )
        logger.error(f"Error creating PR: {e}")
        raise e


@stub.function(image=image, keep_warm=1)
@modal.web_endpoint(method="POST")
async def entrypoint(request: Request):
    body = await request.form()
    request = SlackSlashCommandRequest(**dict(body))
    reply_slack.spawn(request)
    return Response(status_code=200)


@stub.function(image=image, keep_warm=1)
@modal.web_endpoint(method="GET")
def install():
    return RedirectResponse(url=slack_install_link)


def get_oauth_settings():
    from slack_bolt.oauth.oauth_settings import OAuthSettings

    return OAuthSettings(
        client_id=os.environ["SLACK_CLIENT_ID"],
        client_secret=os.environ["SLACK_CLIENT_SECRET"],
        scopes=[
            "app_mentions:read",
            "channels:history",
            "channels:read",
            "chat:write",
            "chat:write.customize",
            "chat:write.public",
            "commands",
            "groups:read",
            "im:read",
            "users.profile:read",
            "users:read",
            "incoming-webhook",
            "mpim:read",
        ],
        install_page_rendering_enabled=False,
        installation_store=MongoDBInstallationStore(),
    )


@stub.function(image=image, secrets=secrets, keep_warm=1)
@modal.asgi_app(label=PREFIX + "-slack-bot")
def _asgi_app():
    from slack_bolt import App
    from slack_bolt.adapter.fastapi import SlackRequestHandler

    slack_app = App(oauth_settings=get_oauth_settings())

    fastapi_app = FastAPI()
    handler = SlackRequestHandler(slack_app)

    @slack_app.event("url_verification")
    def handle_url_verification(body, logger):
        challenge = body.get("challenge")
        return {"challenge": challenge}

    @slack_app.event("app_mention")
    def handle_app_mentions(body, say, client):
        print("here!")

    @slack_app.event("message")
    def handle_message(body, ack, message, client):
        ack()
        print(message)
        if "thread_ts" in message:
            # checking if the message is in a thread
            conversation = client.conversations_replies(
                channel=message["channel"], ts=message["thread_ts"]
            )
            thread_messages = conversation["messages"]
            if thread_messages:
                # checking if the thread has non-zero messages
                bot_profile = thread_messages[0].get("bot_profile")
                if thread_messages[-1].get("bot_profile"):
                    # prevent bots from replying to themselves
                    return
                if bot_profile and bot_profile.get("name") == "Sweep":
                    # checking that the message is from Sweep
                    channel_name = client.conversations_info(
                        channel=message["channel"]
                    )["channel"]["name"]
                    reply_slack.call(
                        SlackSlashCommandRequest(
                            channel_id=message["channel"],
                            channel_name=channel_name,
                            text=message["text"],
                            user_name=message["user"],
                            user_id=message["user"],
                            team_id=message["team"],
                            is_enterprise_install=False,
                        ),
                        thread_ts=message["thread_ts"],
                    )

    @slack_app.command("/sweep")
    def sweep(ack, respond, command, client):
        print(ack, respond, command, client)
        ack()
        respond("I'm working on it!")
        reply_slack.spawn(SlackSlashCommandRequest(**command))

    @fastapi_app.post("/")
    async def root(request: Request):
        return await handler.handle(request)

    @fastapi_app.get("/slack/install")
    async def oauth_start(request: Request):
        return await handler.handle(request)

    @fastapi_app.get("/slack/oauth_redirect")
    async def oauth_callback(request: Request):
        return await handler.handle(request)

    return fastapi_app
