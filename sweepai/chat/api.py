from functools import wraps
import time
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
from sweepai.agents.modify import modify

from sweepai.agents.modify_utils import get_error_message_dict, validate_and_parse_function_call
from sweepai.agents.search_agent import extract_xml_tag
from sweepai.chat.search_prompts import relevant_snippets_message, relevant_snippet_template, anthropic_system_message, function_response, pr_format, relevant_snippets_message_for_pr, openai_system_message, query_optimizer_system_prompt, query_optimizer_user_prompt, openai_format_message, anthropic_format_message
from sweepai.config.client import SweepConfig
from sweepai.config.server import CACHE_DIRECTORY, DOCKER_ENABLED, GITHUB_APP_ID, GITHUB_APP_PEM
from sweepai.core.chat import ChatGPT, call_llm
from sweepai.core.entities import FileChangeRequest, Message, Snippet, fuse_snippets
from sweepai.core.pull_request_bot import get_pr_summary_for_chat
from sweepai.core.review_utils import split_diff_into_patches
from sweepai.dataclasses.check_status import CheckStatus, gha_to_check_status, gha_to_message
from sweepai.dataclasses.code_suggestions import CodeSuggestion
from sweepai.handlers.on_check_suite import get_failing_docker_logs
from sweepai.handlers.on_failing_github_actions import handle_failing_github_actions
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.github_utils import ClonedRepo, CustomGithub, MockClonedRepo, clean_branch_name, commit_multi_file_changes, create_branch, get_github_client, get_installation_id
from sweepai.utils.event_logger import posthog
from sweepai.utils.str_utils import extract_objects_from_string, get_hash
from sweepai.utils.streamable_functions import streamable
from sweepai.utils.ticket_rendering_utils import get_failing_gha_logs
from sweepai.utils.ticket_utils import prep_snippets
from sweepai.utils.timer import Timer

app = FastAPI()

auth_cache = Cache(f'{CACHE_DIRECTORY}/auth_cache') 
repo_cache = f"{CACHE_DIRECTORY}/repos"
message_cache = f"{CACHE_DIRECTORY}/messages"

os.makedirs(message_cache, exist_ok=True)

DEFAULT_K = 8

def get_cloned_repo(
    repo_name: str,
    access_token: str,
    branch: str = None,
    messages: list[Message] = [],
):
    org_name, repo = repo_name.split("/")
    if branch:
        cloned_repo = ClonedRepo(
            repo_name,
            token=access_token,
            installation_id=get_cached_installation_id(org_name)
        )
        cloned_repo.branch = branch
        try:
            cloned_repo.git_repo.git.checkout(branch)
        except Exception as e:
            logger.warning(f"Error checking out branch {branch}: {e}. Trying to checkout PRs.")
            for message in messages:
                for pull in message.annotations["pulls"]:
                    if pull["branch"] == branch:
                        pr = cloned_repo.repo.get_pull(pull["number"])
                        sha = pr.head.sha
                        cloned_repo.git_repo.git.fetch("origin", sha)
                        cloned_repo.git_repo.git.checkout(sha)
                        logger.info(f"Checked out PR {pull['number']} with SHA {sha}")
                        return cloned_repo
            raise Exception(f"Branch {branch} not found")
    else:
        cloned_repo = MockClonedRepo(f"{repo_cache}/{repo}", repo_name, token=access_token)
        cloned_repo.git_repo.git.pull()
    return cloned_repo

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

def get_cached_installation_id(org_name: str) -> str:
    return get_installation_id(org_name)

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
    
@app.post("/backend/search")
def search_codebase_endpoint(
    repo_name: str = Body(...),
    query: str = Body(...),
    annotations: dict = Body({}),
    access_token: str = Depends(get_token_header),
    branch: str = Body(None),
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
            branch=branch,
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
    branch: str = None,
    metadata: dict = {},
):
    org_name, repo = repo_name.split("/")
    if not os.path.exists(f"{repo_cache}/{repo}") and not branch:
        yield "Cloning repository...", []
        print(f"Cloning {repo_name} to {repo_cache}/{repo}")
        git.Repo.clone_from(f"https://x-access-token:{access_token}@github.com/{repo_name}", f"{repo_cache}/{repo}")
        print(f"Cloned {repo_name} to {repo_cache}/{repo}")
        yield "Repository cloned.", []
        cloned_repo = MockClonedRepo(f"{repo_cache}/{repo}", repo_name, token=access_token)
    else:
        yield f"Cloning into {repo_name}:{branch}...", []
        cloned_repo = get_cloned_repo(repo_name, access_token, branch, [Message(
            content=query,
            role="user",
            annotations=annotations,
        )])
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
        access_token,
        use_optimized_query=not bool(annotations["pulls"]),
    ):
        yield message, snippets

@streamable
def search_codebase(
    repo_name: str,
    query: str,
    access_token: str,
    use_optimized_query: bool = True,
):
    with Timer() as timer:
        org_name, repo = repo_name.split("/")
        if not os.path.exists(f"{repo_cache}/{repo}"):
            print(f"Cloning {repo_name} to {repo_cache}/{repo}")
            git.Repo.clone_from(f"https://x-access-token:{access_token}@github.com/{repo_name}", f"{repo_cache}/{repo}")
            print(f"Cloned {repo_name} to {repo_cache}/{repo}")
        cloned_repo = MockClonedRepo(f"{repo_cache}/{repo}", repo_name, token=access_token)
        cloned_repo.pull()

        if use_optimized_query:
            yield "Optimizing query...", []
            query = call_llm(
                system_prompt=query_optimizer_system_prompt,
                user_prompt=query_optimizer_user_prompt,
                params={"query": query},
                use_openai=True
            ).strip().removeprefix("Search query:").strip()
            yield f"Optimized query: {query}", []

        for message, snippets in prep_snippets.stream(
            cloned_repo, query, 
            use_multi_query=False,
            NUM_SNIPPETS_TO_KEEP=0,
            skip_analyze_agent=True
        ):
            if use_optimized_query:
                yield f"{message} (optimized query: {query})", snippets
            else:
                yield message, snippets
    snippets = fuse_snippets(snippets)
    yield "Fused snippets.", snippets
    logger.debug(f"Preparing snippets took {timer.time_elapsed} seconds")
    return snippets

@app.post("/backend/chat")
def chat_codebase(
    repo_name: str = Body(...),
    messages: list[Message] = Body(...),
    snippets: list[Snippet] = Body(...),
    model: str = Body(...),
    branch: str = Body(None),
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
        branch=branch,
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
    branch: str = None,
):
    EXPAND_SIZE = 100
    if not snippets:
        raise ValueError("No snippets were sent.")
    org_name, repo = repo_name.split("/")
    cloned_repo = get_cloned_repo(repo_name, access_token, branch, messages)
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
        if message.role == "user":
            message.content = message.content.strip()
        if message.role == "function":
            message.role = "user"
        if message.function_call:
            message.function_call = None # pass certain validations
        if message.annotations:
            new_pr_snippets, skipped_pr_snippets, pulls_messages = get_pr_snippets(
                repo_name,
                message.annotations,
                cloned_repo,
            )
            pr_snippets.extend(new_pr_snippets)
            if pulls_messages:
                message.content += "\n\nPull requests:\n" + pulls_messages + f"\n\nBe sure to summarize the contents of the pull request during the analysis phase separately from other relevant files.\n\nRemember, the user's request was:\n\n<message>\n{message.content}\n</message>"
    
    if pr_snippets:
        relevant_pr_snippets: list[Snippet] = []
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
                    content=snippet.expand(EXPAND_SIZE).get_snippet(add_lines=False, add_ellipsis=False)
                )
                for i, snippet in enumerate(relevant_pr_snippets)
            ]),
            joined_relevant_snippets="\n".join([
                relevant_snippet_template.format(
                    i=i,
                    file_path=snippet.file_denotation,
                    content=snippet.expand(EXPAND_SIZE).get_snippet(add_lines=False, add_ellipsis=False)
                )
                for i, snippet in enumerate(other_relevant_snippets)
            ]),
            repo_specific_description=repo_specific_description
        )

    chat_gpt.messages = [
        Message(
            content=chat_gpt.messages[0].content,
            role="system"
        ),
        Message(
            content=snippets_message,
            role="user"
        ),
        *messages[:-1],
    ]

    if len(messages) <= 2:
        chat_gpt.messages.append(
            Message(
                content=openai_format_message if use_openai else anthropic_format_message,
                role="user",
            )
        )
    
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
        new_messages = []

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
                if len(result_string) < 50:
                    continue
                current_string, *_ = result_string.split("<function_call>")
                if "<analysis>" in current_string:
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
                else:
                    current_messages = [
                        Message(
                            content=result_string,
                            role="assistant",
                        )
                    ]
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

        message_content = new_messages[-1].content
        code_suggestions_raw, _ = extract_objects_from_string(message_content, "code_change", ["file_path", "original_code", "new_code"])
        # combine additions of the same file together
        new_code_suggestions_raw = []
        for code_suggestion in code_suggestions_raw:
            fcr = next((fcr for fcr in new_code_suggestions_raw if fcr["file_path"] == code_suggestion["file_path"] and fcr["original_code"] == code_suggestion["original_code"] == ""), None)
            if fcr:
                fcr["new_code"] += "\n\n" + code_suggestion["new_code"].lstrip("\n")
            else:
                new_code_suggestions_raw.append(code_suggestion)
        code_suggestions_raw = new_code_suggestions_raw
        if code_suggestions_raw:
            new_messages[-1].annotations = {
                "codeSuggestions": [
                    {
                        "filePath": code_suggestion["file_path"],
                        "originalCode": code_suggestion["original_code"],
                        "newCode": code_suggestion["new_code"],
                        "state": "pending",
                        "error": None
                    } for code_suggestion in code_suggestions_raw
                ]
            }
        
        # validating
        file_change_requests = []
        for code_suggestion in code_suggestions_raw:
            try:
                cloned_repo.get_contents(code_suggestion["file_path"])
                change_type = "modify"
            except Exception as _e:
                change_type = "create"
            file_change_requests.append(
                FileChangeRequest(
                    filename=code_suggestion["file_path"],
                    instructions=f"<original_code>\n{code_suggestion['original_code']}\n</original_code>\n<new_code>\n{code_suggestion['new_code']}\n</new_code>",
                    change_type=change_type
                )
            )
        error_messages_dict = get_error_message_dict(
            file_change_requests=file_change_requests,
            cloned_repo=cloned_repo
        )

        for i, error_message in error_messages_dict.items():
            new_messages[-1].annotations["codeSuggestions"][i]["error"] = error_message
        
        yield new_messages

        posthog.capture(metadata["username"], "chat_codebase complete", properties={
            **metadata,
            "messages": [message.model_dump() for message in messages],
        })
    
    def postprocessed_stream(*args, **kwargs):
        previous_state = []
        try:
            for messages in stream_state(*args, **kwargs):
                current_state = [
                    message.model_dump()
                    for message in messages
                ]
                patch = jsonpatch.JsonPatch.from_diff(previous_state, current_state)
                if patch:
                    yield patch.to_string()
                previous_state = current_state
        except Exception as e:
            yield json.dumps([
                {
                    "op": "error",
                    "value": "ERROR\n\n" + str(e)
                }
            ])

    return StreamingResponse(
        postprocessed_stream(
            messages[-1].content,
            snippets,
            messages,
            access_token,
            metadata,
            model,
            use_openai=use_openai,
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

@app.post("/backend/autofix")
async def autofix(
    repo_name: str = Body(...),
    code_suggestions: list[CodeSuggestion] = Body(...),
    branch: str = Body(None),
    access_token: str = Depends(get_token_header)
):# -> dict[str, Any] | StreamingResponse:
    # for debugging with rerun_chat_modify_direct.py
    # from dataclasses import asdict
    # data = [asdict(query) for query in code_suggestions]
    # with open("code_suggestions.json", "w") as file:
    #     json.dump(data, file, indent=4)
    with Timer() as timer:
        g = get_authenticated_github_client(repo_name, access_token)
    logger.debug(f"Getting authenticated GitHub client took {timer.time_elapsed} seconds")
    if not g:
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    
    org_name, repo = repo_name.split("/")
    installation_id = get_installation_id(org_name, GITHUB_APP_PEM, GITHUB_APP_ID)
    cloned_repo = ClonedRepo(
        repo_name,
        installation_id=installation_id,
        token=access_token,
        branch=branch
    )

    file_change_requests = []

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

    def stream():
        try:
            for stateful_code_suggestions in modify.stream(
                fcrs=file_change_requests,
                request="",
                cloned_repo=cloned_repo,
                relevant_filepaths=[code_suggestion.file_path for code_suggestion in code_suggestions],
            ):
                yield json.dumps([stateful_code_suggestion.__dict__ for stateful_code_suggestion in stateful_code_suggestions])
        except Exception as e:
            yield json.dumps({"error": str(e)})
            raise e

    return StreamingResponse(stream())

# TODO: refactor all the PR stuff together
# TODO: refactor all the github client stuff

@app.post("/backend/create_pull")
async def create_pull(
    repo_name: str = Body(...),
    file_changes: dict[str, str] = Body(...),
    branch: str = Body(...),
    title: str = Body(...),
    body: str = Body(...),
    base_branch: str = Body(""),
    access_token: str = Depends(get_token_header)
):
    with Timer() as timer:
        g = get_authenticated_github_client(repo_name, access_token)
    logger.debug(f"Getting authenticated GitHub client took {timer.time_elapsed} seconds")
    if not g:
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    
    org_name, repo_name_ = repo_name.split("/")
    
    _token, g = get_github_client_from_org(org_name) # TODO: handle users as well
    
    repo = g.get_repo(repo_name)
    base_branch = base_branch or repo.default_branch
    
    new_branch = create_branch(repo, branch, base_branch)
    
    cloned_repo = MockClonedRepo(
        f"{repo_cache}/{repo_name_}",
        repo_name,
        token=access_token,
        repo=repo
    )

    commit_multi_file_changes(
        cloned_repo,
        file_changes,
        commit_message=f"Updated {len(file_changes)} files",
        branch=new_branch,
    )
    
    title = title or "Sweep AI Pull Request"
    pull_request = repo.create_pull(
        title=title,
        body=body,
        head=new_branch,
        base=base_branch,
    )
    g = get_authenticated_github_client(repo_name, access_token)
    pull_request.add_to_assignees(g.get_user().login)
    file_diffs = pull_request.get_files()

    return {
        "success": True,
        "pull_request": {
            "number": pull_request.number,
            "repo_name": repo_name,
            "title": title,
            "body": body,
            "labels": [],
            "status": "open",
            "file_diffs": [
                {
                    "sha": file.sha,
                    "filename": file.filename,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                    "changes": file.changes,
                    "blob_url": file.blob_url,
                    "raw_url": file.raw_url,
                    "contents_url": file.contents_url,
                    "patch": file.patch,
                    "previous_filename": file.previous_filename,
                }
                for file in file_diffs
            ],
        },
        "new_branch": new_branch
    }

@app.post("/backend/commit_to_pull")
async def commit_to_pull(
    repo_name: str = Body(...),
    file_changes: dict[str, str] = Body(...),
    pr_number: str = Body(...),
    base_branch: str = Body(""),
    commit_message: str = Body(""),
    access_token: str = Depends(get_token_header)
):
    with Timer() as timer:
        g = get_authenticated_github_client(repo_name, access_token)
    logger.debug(f"Getting authenticated GitHub client took {timer.time_elapsed} seconds")
    if not g:
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    
    org_name, repo_name_ = repo_name.split("/")
    
    _token, g = get_github_client_from_org(org_name) # TODO: handle users as well
    
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(int(pr_number))
    base_branch = base_branch or repo.default_branch
    
    cloned_repo = MockClonedRepo(
        f"{repo_cache}/{repo_name_}",
        repo_name,
        token=access_token,
        repo=repo
    )
    commit_message = commit_message or f"Updated {len(file_changes)} files"
    commit_multi_file_changes(
        cloned_repo,
        file_changes,
        commit_message=commit_message,
        branch=pr.head.ref,
    )
    
    title = pr.title or "Sweep AI Pull Request"
    file_diffs = pr.get_files()

    return {
        "success": True,
        "pull_request": {
            "number": pr.number,
            "repo_name": repo_name,
            "title": title,
            "body": pr.body,
            "labels": [],
            "status": "open",
            "file_diffs": [
                {
                    "sha": file.sha,
                    "filename": file.filename,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                    "changes": file.changes,
                    "blob_url": file.blob_url,
                    "raw_url": file.raw_url,
                    "contents_url": file.contents_url,
                    "patch": file.patch,
                    "previous_filename": file.previous_filename,
                }
                for file in file_diffs
            ],
        },
        "new_branch": pr.head.ref
    }

@app.post("/backend/create_pull_metadata")
async def create_pull_metadata(
    repo_name: str = Body(...),
    modify_files_dict: dict = Body(...),
    messages: list[Message] = Body(...),
    access_token: str = Depends(get_token_header)
):
    with Timer() as timer:
        g = get_authenticated_github_client(repo_name, access_token)
    logger.debug(f"Getting authenticated GitHub client took {timer.time_elapsed} seconds")
    if not g:
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}

    title, description = get_pr_summary_for_chat(
        repo_name=repo_name,
        messages=messages,
        modify_files_dict=modify_files_dict,
    )

    return {
        "success": True,
        "title": title,
        "description": description,
        "branch": clean_branch_name(title),
    }

@app.post("/backend/validate_pull")
async def validate_pull(
    repo_name: str = Body(...),
    pull_request_number: int = Body(...),
    access_token: str = Depends(get_token_header)
):
    with Timer() as timer:
        g = get_authenticated_github_client(repo_name, access_token)
    logger.debug(f"Getting authenticated GitHub client took {timer.time_elapsed} seconds")
    if not g:
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    
    org_name, repo_name_ = repo_name.split("/")
    repo = g.get_repo(repo_name)
    pull_request = repo.get_pull(int(pull_request_number))

    cloned_repo = get_cloned_repo(repo_name, access_token, pull_request.head.ref)
    installation_id = get_installation_id(org_name, GITHUB_APP_PEM, GITHUB_APP_ID)
    current_commit = pull_request.head.sha

    def stream():
        try:
            all_statuses: list[CheckStatus] = []
            docker_statuses: list[CheckStatus] = []
            if DOCKER_ENABLED:
                for docker_statuses in get_failing_docker_logs.stream(cloned_repo):
                    yield json.dumps(docker_statuses)
            any_failed = not all_statuses or any(status["succeeded"] is False for status in docker_statuses)
            if not any_failed:
                for _ in range(60 * 6):
                    runs = list(repo.get_commit(current_commit).get_check_runs())
                    suite_runs = list(repo.get_workflow_runs(branch=pull_request.head.ref, head_sha=pull_request.head.sha))
                    suite_statuses: list[CheckStatus] = [
                        {
                            "message": gha_to_message[run.status],
                            "stdout": "", # TODO, fille this in
                            "succeeded": gha_to_check_status[run.status],
                            "status": gha_to_check_status[run.status],
                            "llm_message": "",
                            "container_name": run.name,
                        }
                        for run in sorted(suite_runs, key=lambda run: run.name)
                    ]
                    yield json.dumps(docker_statuses + suite_statuses)
                    if all([run.conclusion in ["success", "skipped", None] and \
                            run.status not in ["in_progress", "waiting", "pending", "requested", "queued"] for run in runs]):
                        logger.info("All Github Actions have succeeded or have no result.")
                        break
                    if not any([run.conclusion == "failure" for run in runs]):
                        time.sleep(10)
                        continue
                    for i, run in enumerate(sorted(suite_runs, key=lambda run: run.name)):
                        if run.conclusion == "failure":
                            failed_logs = get_failing_gha_logs(
                                [run],
                                installation_id,
                            )
                            suite_statuses[i]["stdout"] = failed_logs
                            suite_statuses[i]["succeeded"] = False
                            suite_statuses[i]["status"] = "failure"
                            suite_statuses[i]["llm_message"] = failed_logs
                            yield json.dumps(docker_statuses + suite_statuses)
                    logger.info("Github Actions failed!")
                    break
        except Exception as e:
            yield json.dumps({"error": str(e)})
            raise e

    return StreamingResponse(stream())

@app.post("/backend/fix_pull")
async def fix_pull(
    repo_name: str = Body(...),
    pull_request_number: int = Body(...),
    problem_statement: str = Body(...),
    failing_logs: str = Body(...),
    snippets: list[Snippet] = Body(...),
    access_token: str = Depends(get_token_header)
):
    """
    Temporarily disabled
    """
    with Timer() as timer:
        g = get_authenticated_github_client(repo_name, access_token)
    logger.debug(f"Getting authenticated GitHub client took {timer.time_elapsed} seconds")
    if not g:
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    
    org_name, repo_name_ = repo_name.split("/")
    commit = handle_failing_github_actions(
        problem_statement=problem_statement,
        failing_logs=failing_logs,
        repo=g.get_repo(repo_name),
        pull_request=g.get_repo(repo_name).get_pull(pull_request_number),
        user_token=access_token,
        username=Github(access_token).get_user().login,
        installation_id=get_installation_id(org_name, GITHUB_APP_PEM, GITHUB_APP_ID),
    )

    return commit

@app.post("/backend/messages/save")
async def write_message_to_disk(
    repo_name: str = Body(...),
    messages: list[Message] = Body(...),
    snippets: list[Snippet] = Body(...),
    original_code_suggestions: list = Body([]),
    code_suggestions: list = Body([]),
    pull_request: dict | None = Body(None),
    pull_request_title: str = Body(""),
    pull_request_description: str = Body(""),
    message_id: str = Body(""),
    user_mentioned_pull_request: dict | None = Body(None),
    user_mentioned_pull_requests: list[dict] | None = Body(None),
    commit_to_pr: str= Body("false"),
):
    if not message_id:
        message_id = str(uuid.uuid4())
    try:
        data = {
            "repo_name": repo_name,
            "messages": [message.model_dump() for message in messages],
            "snippets": [snippet.model_dump() for snippet in snippets],
            "original_code_suggestions": [code_suggestion.__dict__ if isinstance(code_suggestion, CodeSuggestion) else code_suggestion for code_suggestion in original_code_suggestions],
            "code_suggestions": [code_suggestion.__dict__ if isinstance(code_suggestion, CodeSuggestion) else code_suggestion for code_suggestion in code_suggestions],
            "pull_request": pull_request,
            "user_mentioned_pull_request": user_mentioned_pull_request,
            "user_mentioned_pull_requests": user_mentioned_pull_requests,
            "pull_request_title": pull_request_title,
            "pull_request_description": pull_request_description,
            "commit_to_pr": commit_to_pr,
        }
        with open(f"{CACHE_DIRECTORY}/messages/{message_id}.json", "w") as file:
            json.dump(data, file)
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

