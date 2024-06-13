from functools import wraps
import traceback
from typing import Any, Callable
import uuid
from diskcache import Cache
import jsonpatch
from copy import deepcopy
import json
import os
from fastapi import Body, Depends, FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
import git
from github import Github
from loguru import logger
import yaml

from sweepai.agents.modify_utils import validate_and_parse_function_call
from sweepai.agents.search_agent import extract_xml_tag
from sweepai.chat.search_prompts import relevant_snippets_message, relevant_snippet_template, anthropic_system_message, function_response, anthropic_format_message, pr_format, relevant_snippets_message_for_pr, openai_format_message, openai_system_message
from sweepai.config.client import SweepConfig
from sweepai.config.server import CACHE_DIRECTORY
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet
from sweepai.core.review_utils import split_diff_into_patches
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.github_utils import CustomGithub, MockClonedRepo, get_github_client, get_installation_id
from sweepai.utils.event_logger import posthog
from sweepai.utils.str_utils import get_hash
from sweepai.utils.streamable_functions import streamable
from sweepai.utils.ticket_utils import prep_snippets
from sweepai.utils.timer import Timer

app = FastAPI()

auth_cache = Cache(f'{CACHE_DIRECTORY}/auth_cache') 
repo_cache = f"{CACHE_DIRECTORY}/repos"
message_cache = f"{CACHE_DIRECTORY}/messages"

os.makedirs(message_cache, exist_ok=True)

DEFAULT_K = 8

def get_pr_snippets(
    repo_name: str,
    annotations: dict,
    cloned_repo: MockClonedRepo,
):
    pr_snippets = []
    skipped_pr_snippets = []
    sweep_config = SweepConfig()
    pulls = annotations.get("pulls", [])
    pulls_messages = ""
    for pull in pulls:
        patch = pull["file_diffs"]
        diff_patch = ""
        # Filters copied from get_pr_changes
        for file_data in patch:
            file_path = file_data["filename"]
            if sweep_config.is_file_excluded(file_path):
                continue
            try:
                file_contents = cloned_repo.get_file_contents(file_path)
            except FileNotFoundError:
                logger.warning(f"Error getting file contents for {file_path}")
                continue
            is_file_suitable, reason = sweep_config.is_file_suitable(file_contents)
            if not is_file_suitable:
                continue
            diff = file_data["patch"]
            if file_data["status"] == "added":
                pr_snippets.append(Snippet.from_file(file_path, file_contents))
            elif file_data["status"] == "modified":
                patches = split_diff_into_patches(diff, file_path)
                num_changes_per_patch = [patch.changes.count("\n+") + patch.changes.count("\n-") for patch in patches]
                if max(num_changes_per_patch) > 10 \
                    or file_contents.count("\n") + 1 < 10 * file_data["changes"]:
                    # print(f"adding {file_path}")
                    # print(num_changes_per_patch)
                    # print(file_contents.count("\n"))
                    pr_snippets.append(Snippet.from_file(file_path, file_contents))
                else:
                    skipped_pr_snippets.append(Snippet.from_file(file_path, file_contents))
            if file_data["status"] in ("added", "modified", "removed"):
                diff_patch += f"File: {file_path}\n" + diff.strip("\n") + "\n\n"
        if diff_patch:
            pulls_messages += pr_format.format(
                url=f"https://github.com/{repo_name}/pull/{pull['number']}",
                title=pull["title"],
                body=pull["body"],
                patch=diff_patch.strip("\n")
            ) + "\n\n"
    return pr_snippets, skipped_pr_snippets, pulls_messages

# function to iterate through a dictionary and ensure all values are json serializable
# truncates strings at 500 for sake of readability
def make_serializable(dictionary: dict):
    MAX_STRING_LENGTH = 500
    new_dictionary = {}
    # find any unserializable objects then turn them to strings
    for arg, value in dictionary.items():
        stringified = False
        try:
            _ = json.dumps(value)
            new_dictionary[arg] = value
        except TypeError:
            try:
                new_dictionary[arg] = str(value)[:500]
                stringified = True
            except Exception:
                new_dictionary[arg] = "Unserializable"
        if stringified and len(new_dictionary[arg]) > MAX_STRING_LENGTH:
            new_dictionary[arg] = new_dictionary[arg][:MAX_STRING_LENGTH] + "..."
    return new_dictionary

# IMPORTANT: to use the function decorator your function must have the username as the first param
def posthog_trace(
    function: Callable[..., Any],
):
    @wraps(function)
    def wrapper(
        username: str,
        *args,
        metadata: dict = {},
        **kwargs
    ):
        tracking_id = get_hash()[:10]
        metadata = {**metadata, "tracking_id": tracking_id, "username": username}
        # attach args and kwargs to metadata
        if args:
            args_names = function.__code__.co_varnames[: function.__code__.co_argcount]
            args_dict = dict(zip(args_names[1:], args)) # skip first arg which must be username
            posthog_args = make_serializable(args_dict)
            metadata = {**metadata, **posthog_args}
        if kwargs:
            posthog_kwargs = make_serializable(kwargs)
            if "access_token" in posthog_kwargs:
                del posthog_kwargs["access_token"]
            metadata = {**metadata, **posthog_kwargs}
        metadata = make_serializable(metadata)
        posthog.capture(username, f"{function.__name__} start", properties=metadata)

        try:
            # check if metadata is in the function signature
            if "metadata" in function.__code__.co_varnames[: function.__code__.co_argcount]:
                result = function(
                    username,
                    *args,
                    **kwargs,
                    metadata=metadata
                )
            else:
                result = function(
                    username,
                    *args,
                    **kwargs,
                )
        except Exception as e:
            posthog.capture(username, f"{function.__name__} error", properties={**metadata, "error": str(e), "trace": traceback.format_exc()})
            raise e
        else:
            posthog.capture(username, f"{function.__name__} success", properties=metadata)
            return result
    return wrapper

@auth_cache.memoize(expire=None)
def get_cached_installation_id(org_name: str) -> str:
    return get_installation_id(org_name)

@auth_cache.memoize(expire=60 * 10)
def get_github_client_from_org(org_name: str) -> tuple[str, CustomGithub]:
    return get_github_client(get_cached_installation_id(org_name))

def get_authenticated_github_client(
    repo_name: str,
    access_token: str
):
    # Returns read access, write access, or none
    g = Github(access_token)
    user = g.get_user()
    try:
        repo = g.get_repo(repo_name)
        return g
    except Exception:
        org_name, _ = repo_name.split("/")
        try:
            _token, g = get_github_client_from_org(org_name)
        except Exception as e:
            raise Exception(f"Error getting installation for {repo_name}: {e}. Double-check if the app is installed for this repo.")
        try:
            repo = g.get_repo(repo_name)
        except Exception as e:
            raise Exception(f"Error getting repo {repo_name}: {e}")
        if repo.has_in_collaborators(user.login):
            return g
        else:
            raise Exception(f"User {user.login} does not have the necessary permissions for the repository {repo_name}.")

async def get_token_header(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=400, detail="Invalid token")
    return authorization.removeprefix("Bearer ")

@app.get("/backend/repo")
def check_repo_exists_endpoint(repo_name: str, access_token: str = Depends(get_token_header)):
    try:
        g = get_authenticated_github_client(repo_name, access_token)
    except Exception as e:
        return {"success": False, "error": f"{str(e)}"}

    username = Github(access_token).get_user().login

    token = g.token if isinstance(g, CustomGithub) else access_token

    return check_repo_exists(
        username,
        repo_name,
        token,
        metadata={
            "repo_name": repo_name,
        }
    )

@posthog_trace
def check_repo_exists(
    username: str,
    repo_name: str,
    access_token: str,
    metadata: dict = {},
):
    org_name, repo = repo_name.split("/")
    if os.path.exists(f"{repo_cache}/{repo}"):
        return {"success": True}
    try:
        print(f"Cloning {repo_name} to {repo_cache}/{repo}")
        git.Repo.clone_from(f"https://x-access-token:{access_token}@github.com/{repo_name}", f"{repo_cache}/{repo}")
        print(f"Cloned {repo_name} to {repo_cache}/{repo}")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/backend/search")
def search_codebase_endpoint_get(
    repo_name: str,
    query: str,
    stream: bool = False,
    access_token: str = Depends(get_token_header)
):
    """
    DEPRECATED, use POST instead.
    """
    with Timer() as timer:
        g = get_authenticated_github_client(repo_name, access_token)
    logger.debug(f"Getting authenticated GitHub client took {timer.time_elapsed} seconds")
    if not g:
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    username = Github(access_token).get_user().login
    token = g.token if isinstance(g, CustomGithub) else access_token
    if stream:
        def stream_response():
            yield json.dumps(["Building lexical index...", []])
            for message, snippets in wrapped_search_codebase.stream(
                username,
                repo_name,
                query,
                access_token=token,
                metadata={
                    "repo_name": repo_name,
                    "query": query,
                }
            ):
                yield json.dumps((message, [snippet.model_dump() for snippet in snippets]))
        return StreamingResponse(stream_response())
    else:
        return [snippet.model_dump() for snippet in wrapped_search_codebase(
            username,
            repo_name,
            query,
            access_token=token,
            metadata={
                "repo_name": repo_name,
                "query": query,
            }
        )]
    
@app.post("/backend/search")
def search_codebase_endpoint_post(
    repo_name: str = Body(...),
    query: str = Body(...),
    annotations: dict = Body({}),
    access_token: str = Depends(get_token_header)
):
    with Timer() as timer:
        g = get_authenticated_github_client(repo_name, access_token)
    logger.debug(f"Getting authenticated GitHub client took {timer.time_elapsed} seconds")
    if not g:
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    username = Github(access_token).get_user().login
    token = g.token if isinstance(g, CustomGithub) else access_token
    def stream_response():
        yield json.dumps(["Starting search...", []])
        for message, snippets in wrapped_search_codebase.stream(
            username,
            repo_name,
            query,
            token,
            annotations=annotations,
            metadata={
                "repo_name": repo_name,
                "query": query,
            }
        ):
            yield json.dumps((message, [snippet.model_dump() for snippet in snippets]))
    return StreamingResponse(stream_response())

@streamable
@posthog_trace
def wrapped_search_codebase(
    username: str,
    repo_name: str,
    query: str,
    access_token: str,
    annotations: dict = {},
    metadata: dict = {},
):
    org_name, repo = repo_name.split("/")
    if not os.path.exists(f"{repo_cache}/{repo}"):
        yield "Cloning repository...", []
        print(f"Cloning {repo_name} to {repo_cache}/{repo}")
        git.Repo.clone_from(f"https://x-access-token:{access_token}@github.com/{repo_name}", f"{repo_cache}/{repo}")
        print(f"Cloned {repo_name} to {repo_cache}/{repo}")
        yield "Repository cloned.", []
        cloned_repo = MockClonedRepo(f"{repo_cache}/{repo}", repo_name, token=access_token)
    else:
        cloned_repo = MockClonedRepo(f"{repo_cache}/{repo}", repo_name, token=access_token)
        cloned_repo.pull()
        yield "Repository pulled.", []
    if annotations:
        yield "Getting pull request snippets...", []
        pr_snippets, skipped_pr_snippets, pulls_messages = get_pr_snippets(
            repo_name,
            annotations,
            cloned_repo,
        )
        if pulls_messages.count("<pull_request>") > 1:
            query += "\n\nHere are the mentioned pull request(s):\n\n" + pulls_messages
        else:
            query += "\n\n" + pulls_messages
        yield "Got pull request snippets.", []
    for message, snippets in search_codebase.stream(
        repo_name,
        query,
        access_token
    ):
        yield message, snippets

@streamable
def search_codebase(
    repo_name: str,
    query: str,
    access_token: str,
):
    with Timer() as timer:
        org_name, repo = repo_name.split("/")
        if not os.path.exists(f"{repo_cache}/{repo}"):
            print(f"Cloning {repo_name} to {repo_cache}/{repo}")
            git.Repo.clone_from(f"https://x-access-token:{access_token}@github.com/{repo_name}", f"{repo_cache}/{repo}")
            print(f"Cloned {repo_name} to {repo_cache}/{repo}")
        cloned_repo = MockClonedRepo(f"{repo_cache}/{repo}", repo_name, token=access_token)
        cloned_repo.pull()
        for message, snippets in prep_snippets.stream(
            cloned_repo, query, 
            use_multi_query=False,
            NUM_SNIPPETS_TO_KEEP=0,
            skip_analyze_agent=True
        ):
            yield message, snippets
    logger.debug(f"Preparing snippets took {timer.time_elapsed} seconds")
    return snippets

@app.post("/backend/chat")
def chat_codebase(
    repo_name: str = Body(...),
    messages: list[Message] = Body(...),
    snippets: list[Snippet] = Body(...),
    model: str = Body(...),
    use_patch: bool = Body(True),
    k: int = Body(DEFAULT_K),
    access_token: str = Depends(get_token_header)
):
    if len(messages) == 0:
        raise ValueError("At least one message is required.")

    g = get_authenticated_github_client(repo_name, access_token)
    assert g

    username = Github(access_token).get_user().login
    token = g.token if isinstance(g, CustomGithub) else access_token

    return chat_codebase_stream(
        username,
        repo_name,
        messages,
        snippets,
        token,
        metadata={
            "repo_name": repo_name,
            "message": messages[-1].content,
            "messages": [message.model_dump() for message in messages],
            "snippets": [snippet.model_dump() for snippet in snippets],
        },
        model=model,
        use_patch=use_patch,
        k=k
    )

# this is messy; its modular so we can move it elsewhere later
def get_repo_specific_description(cloned_repo: MockClonedRepo):
    try:
        sweep_yaml_contents = cloned_repo.get_file_contents("sweep.yaml")
        sweep_yaml = yaml.safe_load(sweep_yaml_contents)
        description = sweep_yaml.get("description", "")
        system_prompt_formatted_description = f"\nThis is a user provided description of the codebase. Keep this in mind if it is relevant to their query:\n<codebase_description>\n{description}\n</codebase_description>\n"
        return system_prompt_formatted_description
    except FileNotFoundError:
        logger.info(f"No .sweep.yaml file present in {cloned_repo.repo_full_name}.")
        return ""
    except Exception as e:
        logger.error(f"Error reading .sweep.yaml file: {e}")
        return ""

@posthog_trace
def chat_codebase_stream(
    username: str,
    repo_name: str,
    messages: list[Message],
    snippets: list[Snippet],
    access_token: str,
    metadata: dict = {},
    k: int = DEFAULT_K,
    model: str = "claude-3-opus-20240229",
    use_patch: bool = False,
):
    EXPAND_SIZE = 100
    if not snippets:
        raise ValueError("No snippets were sent.")
    org_name, repo = repo_name.split("/")
    cloned_repo = MockClonedRepo(f"{repo_cache}/{repo}", repo_name, token=access_token)
    cloned_repo.git_repo.git.pull()
    repo_specific_description = get_repo_specific_description(cloned_repo=cloned_repo)
    use_openai = model.startswith("gpt")
    snippets_message = relevant_snippets_message.format(
        repo_name=repo_name,
        joined_relevant_snippets="\n".join([
            relevant_snippet_template.format(
                i=i,
                file_path=snippet.file_denotation,
                content=snippet.expand(EXPAND_SIZE).get_snippet(add_lines=False)
            )
            for i, snippet in enumerate(snippets)
        ]),
        repo_specific_description=repo_specific_description
    )
    system_message = anthropic_system_message if not model.startswith("gpt") else openai_system_message
    chat_gpt: ChatGPT = ChatGPT.from_system_message_string(
        prompt_string=system_message
    )

    pr_snippets = []
    for message in messages:
        if message.role == "function":
            message.role = "assistant"
        if message.function_call:
            message.function_call = None
        if message.annotations:
            new_pr_snippets, skipped_pr_snippets, pulls_messages = get_pr_snippets(
                repo_name,
                message.annotations,
                cloned_repo,
            )
            pr_snippets.extend(new_pr_snippets)
            if pulls_messages:
                message.content += "\n\nPull requests:\n" + pulls_messages + "\n\nBe sure to summarize the contents of the pull request during the analysis phase separately from other relevant files."
    
    if pr_snippets:
        relevant_pr_snippets = []
        other_relevant_snippets = []
        for snippet in snippets:
            if snippet.file_path in [pr_snippet.file_path for pr_snippet in pr_snippets]:
                relevant_pr_snippets.append(snippet)
            else:
                other_relevant_snippets.append(snippet)
        
        snippets_message = relevant_snippets_message_for_pr.format(
            repo_name=repo_name,
            pr_files="\n".join([
                relevant_snippet_template.format(
                    i=i,
                    file_path=snippet.file_denotation,
                    content=snippet.expand(EXPAND_SIZE).get_snippet(add_lines=False)
                )
                for i, snippet in enumerate(relevant_pr_snippets)
            ]),
            joined_relevant_snippets="\n".join([
                relevant_snippet_template.format(
                    i=i,
                    file_path=snippet.file_denotation,
                    content=snippet.expand(EXPAND_SIZE).get_snippet(add_lines=False)
                )
                for i, snippet in enumerate(other_relevant_snippets)
            ]),
            repo_specific_description=repo_specific_description
        )

    chat_gpt.messages = [
        Message(
            content=snippets_message,
            role="user"
        ),
        *messages[:-1]
    ]

    def stream_state(
        initial_user_message: str,
        snippets: list[Snippet],
        messages: list[Message],
        access_token: str,
        metadata: dict,
        model: str,
        use_openai: bool,
        k: int = DEFAULT_K
    ):
        user_message = initial_user_message
        fetched_snippets = snippets
        new_messages = [
            Message(
                content=snippets_message,
                role="function",
                function_call={
                    "function_name": "search_codebase",
                    "function_parameters": {},
                    "is_complete": True,
                    "snippets": deepcopy(snippets)
                }
            )
        ] if len(messages) <= 2 else []

        yield new_messages

        for _ in range(5):
            stream = chat_gpt.chat_anthropic(
                content=user_message,
                model=model,
                stop_sequences=["</function_call>", "</function_calls>"],
                stream=True,
                use_openai=use_openai
            )
            
            result_string = ""
            user_response = ""
            self_critique = ""
            current_messages = []
            for token in stream:
                if not token:
                    continue
                result_string += token
                current_string, *_ = result_string.split("<function_call>")
                analysis = extract_xml_tag(current_string, "analysis", include_closing_tag=False) or ""
                user_response = extract_xml_tag(current_string, "user_response", include_closing_tag=False) or ""
                self_critique = extract_xml_tag(current_string, "self_critique", include_closing_tag=False)

                current_messages = []
                
                if analysis:
                    current_messages.append(
                        Message(
                            content=analysis,
                            role="function",
                            function_call={
                                "function_name": "analysis",
                                "function_parameters": {},
                                "is_complete": bool(user_response),
                            }
                        )
                    )
                
                if user_response:
                    current_messages.append(
                        Message(
                            content=user_response,
                            role="assistant",
                        )
                    )
                
                if self_critique:
                    current_messages.append(
                        Message(
                            content=self_critique,
                            role="function",
                            function_call={
                                "function_name": "self_critique",
                                "function_parameters": {},
                            }
                        )
                    )
                
                yield [
                    *new_messages,
                    *current_messages
                ]
            
            if current_messages[-1].role == "function":
                current_messages[-1].function_call["is_complete"] = True
            
            new_messages.extend(current_messages)
            
            yield new_messages
            
            chat_gpt.messages.append(
                Message(
                    content=result_string,
                    role="assistant",
                )
            )

            result_string = result_string.replace("<function_calls>", "<function_call>")
            result_string += "</function_call>"
            
            function_call = validate_and_parse_function_call(result_string, chat_gpt)
            
            if function_call:
                yield [
                    *new_messages,
                    Message(
                        content="",
                        role="function",
                        function_call={
                            "function_name": function_call.function_name,
                            "function_parameters": function_call.function_parameters,
                            "is_complete": False,
                        },
                    )
                ]
                
                function_output, new_snippets = handle_function_call(function_call, repo_name, fetched_snippets, access_token, k)
                
                yield [
                    *new_messages,
                    Message(
                        content=function_output,
                        role="function",
                        function_call={
                            "function_name": function_call.function_name,
                            "function_parameters": function_call.function_parameters,
                            "is_complete": True,
                            "snippets": new_snippets
                        }
                    )
                ]

                new_messages.append(
                    Message(
                        content=function_output,
                        role="function",
                        function_call={
                            "function_name": function_call.function_name,
                            "function_parameters": function_call.function_parameters,
                            "is_complete": True,
                            "snippets": new_snippets
                        }
                    )
                )

                user_message = f"<function_output>\n{function_output}\n</function_output>\n\n{function_response}"
            else:
                break
        yield new_messages
        posthog.capture(metadata["username"], "chat_codebase complete", properties={
            **metadata,
            "messages": [message.model_dump() for message in messages],
        })
    
    def postprocessed_stream(*args, use_patch=False, **kwargs):
        previous_state = []
        try:
            for messages in stream_state(*args, **kwargs):
                if not use_patch:
                    yield json.dumps([
                        message.model_dump()
                        for message in messages
                    ])
                else:
                    current_state = [
                        message.model_dump()
                        for message in messages
                    ]
                    patch = jsonpatch.JsonPatch.from_diff(previous_state, current_state)
                    if patch:
                        yield patch.to_string()
                    previous_state = current_state
        except Exception as e:
            print(e)
            yield json.dumps([
                {
                    "op": "error",
                    "value": "ERROR\n\n" + str(e)
                }
            ])

    format_message = anthropic_format_message if not model.startswith("gpt") else openai_format_message
    return StreamingResponse(
        postprocessed_stream(
            f"Here is the user's message:\n<user_message>\n{messages[-1].content}\n</user_message>\n\n" + format_message,
            snippets,
            messages,
            access_token,
            metadata,
            model,
            use_openai=use_openai,
            use_patch=use_patch,
            k=k
        )
    )

def handle_function_call(function_call: AnthropicFunctionCall, repo_name: str, snippets: list[Snippet], access_token: str, k: int = DEFAULT_K):
    if function_call.function_name == "search_codebase":
        if "query" not in function_call.function_parameters:
            return "ERROR\n\nQuery parameter is required."
        new_snippets = search_codebase(
            repo_name=repo_name,
            query=function_call.function_parameters["query"],
            access_token=access_token
        )
        fetched_snippet_denotations = [snippet.denotation for snippet in snippets]
        new_snippets_to_add = [snippet for snippet in new_snippets if snippet.denotation not in fetched_snippet_denotations]
        new_snippets_string = "\n".join([
            relevant_snippet_template.format(
                i=i,
                file_path=snippet.file_path,
                content=snippet.content
            )
            for i, snippet in enumerate(new_snippets_to_add[k::-1])
        ])
        snippets += new_snippets[:k]
        return f"SUCCESS\n\nHere are the relevant files to your search request:\n{new_snippets_string}", new_snippets_to_add[:k]
    else:
        return "ERROR\n\nTool not found.", []

@app.post("/backend/messages/save")
async def write_message_to_disk(
    repo_name: str = Body(...),
    messages: list[Message] = Body(...),
    snippets: list[Snippet] = Body(...),
    message_id: str = Body(""),
):
    if not message_id:
        message_id = str(uuid.uuid4())
    try:
        with open(f"{CACHE_DIRECTORY}/messages/{message_id}.json", "w") as file:
            json.dump({
                "repo_name": repo_name,
                "messages": [message.model_dump() for message in messages],
                "snippets": [snippet.model_dump() for snippet in snippets]
            }, file)
        return {"status": "success", "message": "Message written to disk successfully.", "message_id": message_id}
    except Exception as e:
        logger.error(f"Failed to write message to disk: {str(e)}")
        return {"status": "error", "message": "Failed to write message to disk."}

@app.get("/backend/messages/load/{message_id}")
async def read_message_from_disk(
    message_id: str,
):
    try:
        with open(f"{CACHE_DIRECTORY}/messages/{message_id}.json", "r") as file:
            message_data = json.load(file)
        return {
            "status": "success",
            "message": "Message read from disk successfully.",
            "data": message_data
        }
    except FileNotFoundError:
        return {"status": "error", "message": "Message not found."}
    except Exception as e:
        logger.error(f"Failed to read message from disk: {str(e)}")
        return {"status": "error", "message": "Failed to read message from disk."}


if __name__ == "__main__":
    import fastapi.testclient
    client = fastapi.testclient.TestClient(app)
    # response = client.get("/search?repo_name=sweepai/sweep&query=backend")
    # print(response.text)
    messages = [
        Message(
            content="Where is the backend code?",
            role="user"
        )
    ]
    snippets = [
        Snippet(
            content="def get_backend():\n    return 'backend'",
            file_path="backend.py",
            start=0,
            end=1,
        )
    ]
    response = client.post("/chat", json={
        "repo_name": "sweepai/sweep",
        "messages": [message.model_dump() for message in messages],
        "snippets": [snippet.model_dump() for snippet in snippets]
    })
    print(response.text)

