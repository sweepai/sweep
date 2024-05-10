from copy import deepcopy
import json
import os
from fastapi import Body, Depends, FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
import git
from github import Github

from sweepai.agents.modify_utils import validate_and_parse_function_call
from sweepai.agents.search_agent import extract_xml_tag
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.github_utils import MockClonedRepo, get_installation_id, get_token
from sweepai.utils.ticket_utils import prep_snippets

app = FastAPI()

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
def check_repo_exists(repo_name: str, access_token: str = Depends(get_token_header)):
    if not check_user_authenticated(repo_name, access_token):
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    org_name, repo = repo_name.split("/")
    if os.path.exists(f"/tmp/{repo}"):
        return {"success": True}
    try:
        print(f"Cloning {repo_name} to /tmp/{repo}")
        installation_id = get_installation_id(org_name)
        token = get_token(installation_id)
        git.Repo.clone_from(f"https://x-access-token:{token}@github.com/{repo_name}", f"/tmp/{repo}")
        print(f"Cloned {repo_name} to /tmp/{repo}")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def search_codebase(
    repo_name: str,
    query: str,
):
    org_name, repo = repo_name.split("/")
    if not os.path.exists(f"/tmp/{repo}"):
        print(f"Cloning {repo_name} to /tmp/{repo}")
        installation_id = get_installation_id(org_name)
        token = get_token(installation_id)
        git.Repo.clone_from(f"https://x-access-token:{token}@github.com/{repo_name}", f"/tmp/{repo}")
        print(f"Cloned {repo_name} to /tmp/{repo}")
    cloned_repo = MockClonedRepo(f"/tmp/{repo}", repo_name)
    repo_context_manager = prep_snippets(cloned_repo, query, use_multi_query=False, NUM_SNIPPETS_TO_KEEP=0)
    return repo_context_manager.current_top_snippets

@app.get("/backend/search")
def search_codebase_endpoint(
    repo_name: str,
    query: str,
    access_token: str = Depends(get_token_header)
):
    if not check_user_authenticated(repo_name, access_token):
        return {"success": False, "error": "The repository may not exist or you may not have access to this repository."}
    return [snippet.model_dump() for snippet in search_codebase(repo_name, query)]

example_tool_calls = """Here is an illustrative example of how to use the tools:

To ask questions about the codebase:
<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<query>
How do we the user-provided password hash against the stored hash from the database in the user-authentication service?
</query>
</parameters>
</invoke>
</function_call>

Notice that the `query` parameter is a single, extremely detailed, specific natural language search question.

Here are other examples of good questions to ask:

How are GraphQL mutations constructed for updating a user's profile information, and what specific fields are being updated?
How do the current React components render the product carousel on the homepage, and what library is being used for the carousel functionality?
How do we currently implement the endpoint handler for processing incoming webhook events from Stripe in the backend API, and how are the events being validated and parsed?
What is the structure of the Post model in the blog module?

The above are just illustrative examples. Make sure to provide detailed, specific questions to search for relevant snippets in the codebase and only make one function call."""

function_response = """The above is the output of the function call.

First, list and summarize each file from the codebase provided that is relevant to the user's question. List all beliefs and assumptions previously made that are invalidated by the new information.

Respond in the following format:

### Format

Use GitHub-styled markdown for your responses. You must respond with the following three distinct sections:

# 1. User Response

<user_response>
## Summary
First, list and summarize each file from the codebase provided in the last function output that is relevant to the user's question. You may not need to summarize all provided files.

## New information
Secondly, list all new information that was retrieved from the codebase that is relevant to the user's question, especially if it invalidates any previous beliefs or assumptions.

## Updated answer
Determine if you have sufficient information to answer the user's question. If not, determine the information you need to answer the question completely by making `search_codebase` tool calls.

If so, rewrite your previous response with the new information and any invalidated beliefs or assumptions. Make sure this answer is complete and helpful. Provide code examples, explanations and excerpts wherever possible to provide concrete explanations. When suggesting code changes, write out all the code changes required, indicating the current code and the code to replace it with When suggesting code changes, write out all the code changes required, indicating the current code and the code to replace it with.
</user_response>

# 2. Self-Critique

<self_critique>
Then, self-critique your answer and validate that you have completely answered the user's question. If the user's answer is relatively broad, you are done.

Otherwise, if the user's question is specific, and asks to implement a feature or fix a bug, determine what additional information you need to answer the user's question. Specifically, validate that all interfaces are being used correctly based on the contents of the retrieved files -- if you cannot verify this, then you must find the relevant information such as the correct interface or schema to validate the usage. If you need to search the codebase for more information, such as for how a particular feature in the codebase works, use the `search_codebase` tool in the next section.
</self_critique>

# 3. Function Calls (Optional)

Then, make each function call like so:
<function_calls>
[the list of function calls go here, using the valid XML format for function calls]
</function_calls>""" + example_tool_calls

format_message = """### Format

Use GitHub-styled markdown for your responses. You must respond with the following three distinct sections:

# 1. User Response

<user_response>
## Summary
First, list and summarize each file from the codebase provided that is relevant to the user's question. You may not need to summarize all provided files.

## Answer
Determine if you have sufficient information to answer the user's question. If not, determine the information you need to answer the question completely by making `search_codebase` tool calls.

If so, write a complete helpful response to the user's question oin detail. Make sure this answer is complete and helpful. Provide code examples, explanations and excerpts wherever possible to provide concrete explanations. When suggesting code changes, write out all the code changes required, indicating the current code and the code to replace it with When suggesting code changes, write out all the code changes required, indicating the current code and the code to replace it with.
</user_response>

# 2. Self-Critique

<self_critique>
Then, self-critique your answer and validate that you have completely answered the user's question. If the user's answer is relatively broad, you are done.

Otherwise, if the user's question is specific, and asks to implement a feature or fix a bug, determine what additional information you need to answer the user's question. Specifically, validate that all interfaces are being used correctly based on the contents of the retrieved files -- if you cannot verify this, then you must find the relevant information such as the correct interface or schema to validate the usage. If you need to search the codebase for more information, such as for how a particular feature in the codebase works, use the `search_codebase` tool in the next section.
</self_critique>

# 3. Function Calls (Optional)

Then, make each function call like so:
<function_calls>
[the list of function calls go here, using the valid XML format for function calls]
</function_calls>

""" + example_tool_calls

tools_available = """You have access to the following tools to assist in fulfilling the user request:
<tool_description>
<tool_name>search_codebase</tool_name>
<description>
</description>
<parameters>
<parameter>
<name>query</name>
<type>str</type>
<description>
Single, detailed, specific natural language search question to search the codebase for relevant snippets. This should be in the form of a natural language question, like "What is the structure of the User model in the authentication module?"
</description>
</parameter>
<parameter>
<name>include_docs</name>
<type>str</type>
<description>
(Optional) Include documentation in the search results. Default is false.
</description>
</parameter>
<parameter>
<name>include_tests</name>
<type>str</type>
<description>
(Optional) Include test files in the search results. Default is false.
</description>
</parameter>
</parameters>
</tool_description>

""" + example_tool_calls

system_message = """You are a helpful assistant that will answer a user's questions about a codebase to resolve their issue. You are provided with a list of relevant code snippets from the codebase that you can refer to. You can use this information to help the user solve their issue. You may also make function calls to retrieve additional information from the codebase. 

In this environment, you have access to the following tools to assist in fulfilling the user request:

Once you have collected and analyzed the relevant snippets, use the `submit_task` tool to submit the final response to the user's question.

You MUST call them like this:
<function_call>
<invoke>
<tool_name>$TOOL_NAME</tool_name>
<parameters>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</parameters>
</invoke>
</function_call>

Here are the tools available:

""" + tools_available + "\n\n" + format_message

relevant_snippets_message = """# Codebase
repo: {repo_name}

# Relevant codebase files:
Here are the relevant files from the codebase. We previously summarized each of the files to help you solve the GitHub issue. These will be your primary reference to solve the problem:

<relevant_files>
{joined_relevant_snippets}
</relevant_files>"""

relevant_snippet_template = '''<relevant_file index="{i}">
<file_path>
{file_path}
</file_path>
<source>
{content}
</source>
</relevant_file>'''

@app.post("/backend/chat")
def chat_codebase(
    repo_name: str = Body(...),
    messages: list[Message] = Body(...),
    snippets: list[Snippet] = Body(...),
):
    if len(messages) == 0:
        raise ValueError("At least one message is required.")

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

    def stream_state(initial_user_message: str, snippets: list[Snippet], messages: list[Message]):
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
                stop_sequences=["</function_call>"],
                stream=True
            )
            
            result_string = ""
            user_response = ""
            self_critique = ""
            for token in stream:
                result_string += token
                user_response = extract_xml_tag(result_string, "user_response", include_closing_tag=False) or ""
                self_critique = extract_xml_tag(result_string, "self_critique", include_closing_tag=False)
                
                if self_critique:
                    yield [
                        *new_messages,
                        Message(
                            content=user_response,
                            role="assistant"
                        ),
                        Message(
                            content=self_critique,
                            role="function",
                            function_call={
                                "function_name": "self_critique",
                                "function_parameters": {},
                                "is_complete": False,
                            }
                        ),
                    ]
                else:
                    yield [
                        *new_messages,
                        Message(
                            content=user_response,
                            role="assistant"
                        )
                    ]
            
            new_messages.append(
                Message(
                    content=user_response,
                    role="assistant",
                )
            )

            if self_critique:
                new_messages.append(
                    Message(
                        content=self_critique,
                        role="function",
                        function_call={
                            "function_name": "self_critique",
                            "function_parameters": {},
                            "is_complete": True,
                        }
                    )
                )
            
            yield new_messages
            
            chat_gpt.messages.append(
                Message(
                    content=result_string,
                    role="assistant",
                )
            )
            
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
                
                function_output, new_snippets = handle_function_call(function_call, repo_name, fetched_snippets)
                
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
    
    def postprocessed_stream(*args, **kwargs):
        for messages in stream_state(*args, **kwargs):
            yield json.dumps([
                message.model_dump()
                for message in messages
            ]) + "\n"

    return StreamingResponse(postprocessed_stream(messages[-1].content + "\n\n" + format_message, snippets, messages))

def handle_function_call(function_call: AnthropicFunctionCall, repo_name: str, snippets: list[Snippet]):
    NUM_SNIPPETS = 5
    if function_call.function_name == "search_codebase":
        if "query" not in function_call.function_parameters:
            return "ERROR\n\nQuery parameter is required."
        new_snippets = search_codebase(
            repo_name=repo_name,
            query=function_call.function_parameters["query"]
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
