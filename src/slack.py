import json
import os

from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse

import modal
from pydantic import BaseModel
from pymongo import MongoClient
import requests
from src.core.entities import FileChangeRequest, Function, PullRequest
import slack_sdk
from loguru import logger

from src.core.sweep_bot import SweepBot
from src.utils.github_utils import get_github_client
from src.utils.constants import API_NAME, BOT_TOKEN_NAME, PREFIX, SLACK_NAME
from src.core.prompts import slack_slash_command_prompt
from src.utils.github_utils import get_installation_id
import src.utils.event_logger

image = modal.Image \
    .debian_slim() \
    .apt_install("git") \
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
        "posthog"
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
    Function(
        name="get_relevant_snippets",
        description="Search engine for relevant snippets in the current repo in natural language.",
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

# TODO(sweep): move to constants
slack_app_page = "https://sweepusers.slack.com/apps/A05D69L28HX-sweep"
slack_install_link = "https://slack.com/oauth/v2/authorize?client_id=5364586338420.5448326076609&scope=channels:read,chat:write,chat:write.public,commands,groups:read,im:read,incoming-webhook,mpim:read&user_scope="

class SlackSlashCommandRequest(BaseModel):
    channel_name: str
    channel_id: str
    text: str
    user_name: str
    user_id: str
    team_id: str

@stub.function(
    image=image,
    secrets=secrets,
    timeout=15 * 60,
)
def reply_slack(request: SlackSlashCommandRequest):
    try:
        create_pr = modal.Function.lookup(API_NAME, "create_pr")
        client = None
        for _ in range(3):
            try:
                mongo_client = MongoClient(os.environ['MONGODB_URI'])
                db = mongo_client["slack"]
                collection = db["oauth_tokens"]
                token = collection.find_one({
                    "user_id": request.user_id,
                    "prefix": PREFIX,
                    "workspace_id": request.team_id
                })["access_token"]
                client = slack_sdk.WebClient(token=token)
                break
            except Exception as e:
                logger.error(f"Error fetching token {e}, retrying")
        if client == None: raise Exception("Could not fetch token")
    except Exception as e:
        logger.error(f"Error initializing Slack client: {e}")
        raise e
    
    try:
        channel_info = client.conversations_info(channel=request.channel_id)
        channel_description: str = channel_info['channel']['purpose']['value']
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

        thread = client.chat_postMessage(
            channel=request.channel_id,
            text=f">{request.text}\n- <@{request.user_name}>",
        )
    except Exception as e:
        client.chat_postMessage(
            channel=request.channel_id,
            text=":exclamation: Sorry, something went wrong. Sometimes this is because the Github app is not installed on your repo.",
        )
        raise e

    try:
        logger.info("Fetching relevant snippets...")
        searching_message = client.chat_postMessage(
            channel=request.channel_id,
            text=":mag_right: Searching for relevant snippets...",
            thread_ts=thread["ts"],
        )
        # snippets = default_snippets
        snippets = sweep_bot.search_snippets(
            request.text,
            installation_id=installation_id
        )
        message = ":mag_right: Some relevant snippets I found:\n\n"
        message += "\n".join(f"{snippet.get_slack_link(repo_name)}\n```{snippet.get_preview()}```" for snippet in snippets)
        client.chat_update(
            channel=request.channel_id,
            ts=searching_message["ts"],
            text=message,
        )
        prompt = slack_slash_command_prompt.format(
            relevant_snippets="\n".join([snippet.xml for snippet in snippets]),
            relevant_directories="\n".join([snippet.file_path for snippet in snippets]),
            repo_name=repo_name,
            repo_description=repo.description,
            username=request.user_name,
            query=request.text
        )
        response = sweep_bot.chat(prompt, functions=functions, function_name={"name": "create_pr"})
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
                    thread_ts=thread["ts"],
                )
                additional_snippets = sweep_bot.search_snippets(
                    arguments["query"],
                    installation_id=installation_id
                )
                # additional_snippets = default_snippets
                additional_snippets_message = f":mag_right: Found {len(additional_snippets)} additional snippets with the query \"{arguments['query']}\":\n\n" +  "\n".join(
                    f"{snippet.get_slack_link(repo_name)}\n```{snippet.get_preview()}```" for snippet in additional_snippets
                )
                client.chat_update(
                    channel=request.channel_id,
                    text=additional_snippets_message,
                    ts=search_message["ts"],
                )
                response = sweep_bot.chat(additional_snippets_message, functions=functions)
            elif name == "create_pr":
                title = arguments["title"]
                summary = arguments["summary"]
                branch = arguments["branch"]
                plan = arguments["plan"]
                plan_message = "\n".join(f"• `{file['file_path']}`: {file['instructions']}" for file in plan)
                plan_message = ">" + plan_message.replace("\n", "\n> ")

                creating_pr_message = client.chat_postMessage(
                    channel=request.channel_id,
                    text=pr_format.format(
                        title=title,
                        summary=summary,
                        plan=plan_message
                    ),
                    thread_ts=thread["ts"],
                )
                file_change_requests = [
                    FileChangeRequest(
                        filename=file["file_path"],
                        instructions=file["instructions"],
                        change_type="create" if repo.get_contents(file["file_path"]) is None else "modify",
                    ) for file in plan
                ]
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
                channel=request.channel_id,
                text=response,
                thread_ts=thread["ts"],
            )
    except Exception as e:
        client.chat_postMessage(
            channel=request.channel_id,
            text=":exclamation: Sorry, something went wrong.",
            thread_ts=thread["ts"],
        )
        logger.error(f"Error creating PR: {e}")
        raise e


@stub.function(
    image=image,
    keep_warm=1
)
@modal.web_endpoint(method="POST")
async def entrypoint(request: Request):
    body = await request.form()
    request = SlackSlashCommandRequest(**dict(body))
    reply_slack.spawn(request)
    return Response(status_code=200)


@stub.function(
    image=image,
    secrets=secrets,
    keep_warm=1,
)
@modal.web_endpoint(method="GET")
async def oauth_redirect(request: Request):
    try:
        code = request.query_params.get('code')

        mongo_client = MongoClient(os.environ['MONGODB_URI'])
        db = mongo_client["slack"]
        collection = db["oauth_tokens"]

        if not code:
            raise HTTPException(status_code=400, detail="Missing code parameter")

        response = requests.post('https://slack.com/api/oauth.v2.access', {
            'client_id': os.environ['SLACK_CLIENT_ID'],
            'client_secret': os.environ['SLACK_CLIENT_SECRET'],
            'code': code,
        }).json()

        if not response.get('ok'):
            raise HTTPException(status_code=400, detail="Error obtaining access token")

        logger.info(response)

        result = collection.insert_one({
            "user_id": response["authed_user"]["id"],
            "bot_user_id": response["bot_user_id"],
            "workspace_id": response["team"]["id"],
            "channel": response["incoming_webhook"]["channel"],
            "prefix": PREFIX,
            "access_token": response["access_token"],
        })

        return RedirectResponse(url=slack_app_page)
    except Exception as e:
        logger.error(f"Error with OAuth: {e}")
        raise e

@stub.function(image=image, keep_warm=1)
@modal.web_endpoint(method="GET")
def install():
    return RedirectResponse(url=slack_install_link)
