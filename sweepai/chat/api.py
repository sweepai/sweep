import copy
from functools import wraps
import traceback
from typing import Any, Callable
import jsonpatch
from copy import deepcopy
import json
import os
from fastapi import Body, Depends, FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
import git
from github import Github

from sweepai.agents.modify_utils import validate_and_parse_function_call
from sweepai.agents.search_agent import extract_xml_tag
from sweepai.chat.search_prompts import relevant_snippets_message, relevant_snippet_template, system_message, function_response, format_message
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.github_utils import MockClonedRepo
from sweepai.utils.event_logger import posthog
from sweepai.utils.str_utils import get_hash
from sweepai.utils.ticket_utils import prep_snippets

app = FastAPI()

# function to iterate through a dictionary and ensure all values are json serializable
# truncates strings at 500 for sake of readability
def make_serializable(dictionary: dict):
    MAX_STRING_LENGTH = 500
    new_dictionary = {}
    # find any unserializable objects then turn them to strings
    for arg, value in dictionary.items():
        try:
            new_dictionary[arg] = json.dumps(value)
        except TypeError:
            try:
                new_dictionary[arg] = str(value)[:500]
            except Exception:
                new_dictionary[arg] = "Unserializable"
        if len(new_dictionary[arg]) > MAX_STRING_LENGTH:
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
            metadata = {**metadata, **posthog_kwargs}
        metadata = make_serializable(metadata)
        posthog.capture(username, f"{function.__name__} start", properties=metadata)

        try:
            result = function(
                username,
                *args,
                **kwargs
            )
        except Exception as e:
            posthog.capture(username, f"{function.__name__} error", properties={**metadata, "error": str(e), "trace": traceback.format_exc()})
            raise e
        else:
            posthog.capture(username, f"{function.__name__} success", properties=metadata)
            return result
    return wrapper

def check_user_authenticated(
    repo_name: str,
    access_token: str
) -> str | None:
    # Returns read access, write access, or none
    g = Github(access_token)
    try:
        repo = g.get_repo(repo_name)
        if repo.permissions.admin:
            return "write"
        elif repo.permissions.push:
            return "write"
        elif repo.permissions.pull:
            return "read"
        else:
            return "read"
    except Exception as e:
        print(e)
        return None

async def get_token_header(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=400, detail="Invalid token")
    return authorization.removeprefix("Bearer ")

@app.get("/backend/repo")
def check_repo_exists_endpoint(repo_name: str, access_token: str = Depends(get_token_header)):
    if not check_user_authenticated(repo_name, access_token):
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}

    username = Github(access_token).get_user().login

    return check_repo_exists(
        username,
        repo_name,
        access_token,
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
    if os.path.exists(f"/tmp/{repo}"):
        return {"success": True}
    try:
        print(f"Cloning {repo_name} to /tmp/{repo}")
        git.Repo.clone_from(f"https://x-access-token:{access_token}@github.com/{repo_name}", f"/tmp/{repo}")
        print(f"Cloned {repo_name} to /tmp/{repo}")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/backend/search")
def search_codebase_endpoint(
    repo_name: str,
    query: str,
    access_token: str = Depends(get_token_header)
):
    if not check_user_authenticated(repo_name, access_token):
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    username = Github(access_token).get_user().login
    return [snippet.model_dump() for snippet in wrapped_search_codebase(
        username,
        repo_name,
        query,
        access_token,
        metadata={
            "repo_name": repo_name,
            "query": query,
        }
    )]

@posthog_trace
def wrapped_search_codebase(
    username: str,
    repo_name: str,
    query: str,
    access_token: str,
    metadata: dict = {},
):
    return search_codebase(
        repo_name,
        query,
        access_token
    )

def search_codebase(
    repo_name: str,
    query: str,
    access_token: str,
):
    org_name, repo = repo_name.split("/")
    if not os.path.exists(f"/tmp/{repo}"):
        print(f"Cloning {repo_name} to /tmp/{repo}")
        git.Repo.clone_from(f"https://x-access-token:{access_token}@github.com/{repo_name}", f"/tmp/{repo}")
        print(f"Cloned {repo_name} to /tmp/{repo}")
    cloned_repo = MockClonedRepo(f"/tmp/{repo}", repo_name)
    repo_context_manager = prep_snippets(cloned_repo, query, use_multi_query=False, NUM_SNIPPETS_TO_KEEP=0)
    return repo_context_manager.current_top_snippets

@app.post("/backend/chat")
def chat_codebase(
    repo_name: str = Body(...),
    messages: list[Message] = Body(...),
    snippets: list[Snippet] = Body(...),
    use_patch: bool = Body(False),
    access_token: str = Depends(get_token_header)
):
    if len(messages) == 0:
        raise ValueError("At least one message is required.")
    
    assert check_user_authenticated(repo_name, access_token)

    username = Github(access_token).get_user().login

    return chat_codebase_stream(
        username,
        repo_name,
        messages,
        snippets,
        access_token,
        metadata={
            "repo_name": repo_name,
            "message": messages[-1].content,
            "messages": [message.model_dump() for message in messages],
            "snippets": [snippet.model_dump() for snippet in snippets],
        },
        use_patch=use_patch
    )

@posthog_trace
def chat_codebase_stream(
    username: str,
    repo_name: str,
    messages: list[Message],
    snippets: list[Snippet],
    access_token: str,
    metadata: dict = {},
    use_patch: bool = False,
):
    # Stream
    chat_gpt = ChatGPT.from_system_message_string(
        prompt_string=system_message
    )
    snippets_message = relevant_snippets_message.format(
        repo_name=repo_name,
        joined_relevant_snippets="\n".join([
            relevant_snippet_template.format(
                i=i,
                file_path=snippet.file_path,
                content=snippet.content
            )
            for i, snippet in enumerate(snippets)
        ])
    )
    for message in messages:
        if message.role == "function":
            message.role = "user"
    chat_gpt.messages = [
        Message(
            content=snippets_message,
            role="user"
        ),
        *messages[:-1]
    ]

    def stream_state(initial_user_message: str, snippets: list[Snippet], messages: list[Message], access_token: str):
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
                model="claude-3-opus-20240229",
                stop_sequences=["</function_call>", "</function_calls>"],
                stream=True
            )
            
            result_string = ""
            user_response = ""
            self_critique = ""
            current_messages = []
            for token in stream:
                result_string += token
                analysis = extract_xml_tag(result_string, "analysis", include_closing_tag=False) or ""
                user_response = extract_xml_tag(result_string, "user_response", include_closing_tag=False) or ""
                self_critique = extract_xml_tag(result_string, "self_critique", include_closing_tag=False)

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
                
                function_output, new_snippets = handle_function_call(function_call, repo_name, fetched_snippets, access_token)
                
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
        for messages in stream_state(*args, **kwargs):
            if not use_patch:
                yield json.dumps([
                    message.model_dump()
                    for message in messages
                ]) + "\n"
            else:
                current_state = [
                    message.model_dump()
                    for message in messages
                ]
                patch = jsonpatch.JsonPatch.from_diff(previous_state, current_state)
                if patch:
                    yield patch.to_string() + "\n"
                previous_state = current_state

    return StreamingResponse(
        postprocessed_stream(
            messages[-1].content + "\n\n" + format_message,
            snippets,
            messages,
            access_token,
            use_patch=use_patch
        )
    )

def handle_function_call(function_call: AnthropicFunctionCall, repo_name: str, snippets: list[Snippet], access_token: str):
    NUM_SNIPPETS = 5
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
            for i, snippet in enumerate(new_snippets_to_add[NUM_SNIPPETS::-1])
        ])
        snippets += new_snippets[:NUM_SNIPPETS]
        return f"SUCCESS\n\nHere are the relevant files to your search request:\n{new_snippets_string}", new_snippets_to_add[:NUM_SNIPPETS]
    else:
        return "ERROR\n\nTool not found.", []

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

