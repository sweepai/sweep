import json
import os
from fastapi import Body, FastAPI
from fastapi.responses import StreamingResponse
import git

from sweepai.agents.modify_utils import validate_and_parse_function_call
from sweepai.agents.search_agent import extract_xml_tag
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo
from sweepai.utils.ticket_utils import prep_snippets

app = FastAPI()

@app.get("/repo")
def check_repo_exists(repo_name: str):
    org_name, repo = repo_name.split("/")
    if os.path.exists(f"/tmp/{repo}"):
        return {"success": True}
    try:
        git.clone(f"https://github.com/{repo_name}", f"/tmp/{repo}")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def search_codebase(
    repo_name: str,
    query: str
):
    org_name, repo = repo_name.split("/")
    if not os.path.exists(f"/tmp/{repo}"):
        git.clone(f"https://github.com/{repo_name}", f"/tmp/{repo}")
    cloned_repo = MockClonedRepo(f"/tmp/{repo}", repo_name)
    return prep_snippets(cloned_repo, query, use_multi_query=False, NUM_SNIPPETS_TO_KEEP=0)

@app.get("/search")
def search_codebase_endpoint(
    repo_name: str,
    query: str
):
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

First, summarize each file from the codebase provided that is relevant and how they relate to the user's question. List all beliefs and assumptions previously made that are invalidated by the new information.

Respond in the following format:"""

format_message = """### Format

Use GitHub-styled markdown for your responses. You must respond with the following three distinct sections:

# 1. User Response

<user_response>
First, summarize each file from the codebase provided that is relevant and how they relate to the user's question.
Secondly, write a complete helpful response to the user's question in great detail. Provide code examples and explanations as needed.
</user_response>

# 2. Self-Critique
<self_critique>
Then, self-critique your answer to determine what additional information you need to answer the user's question. Specifically, validate that all interfaces are being used correctly based on the contents of the retrieved files -- if you cannot verify this, then you must find the relevant information such as the correct interface or schema to validate the usage. If you need to search the codebase for more information, such as for how a particular feature in the codebase works, use the `search_codebase` tool in the next section.
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

@app.post("/chat")
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
    chat_gpt.messages = [
        Message(
            content=snippets_message,
            role="user"
        ),
        *messages[:-1]
    ]

    def stream_state(initial_user_message: str, snippets: list[Snippet]):
        user_message = initial_user_message
        fetched_snippets = snippets
        messages = []
        for _ in range(3):
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
                        *messages,
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
                        *messages,
                        Message(
                            content=user_response,
                            role="assistant"
                        )
                    ]
            
            messages.append(
                Message(
                    content=user_response,
                    role="assistant",
                )
            )

            if self_critique:
                messages.append(
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
            
            yield messages
            
            chat_gpt.messages.append(
                Message(
                    content=result_string,
                    role="assistant",
                )
            )
            
            function_call = validate_and_parse_function_call(result_string, chat_gpt)
            
            if function_call:
                yield [
                    *messages,
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
                
                function_output = handle_function_call(function_call, repo_name, fetched_snippets)
                
                yield [
                    *messages,
                    Message(
                        content=function_output,
                        role="function",
                        function_call={
                            "function_name": function_call.function_name,
                            "function_parameters": function_call.function_parameters,
                            "is_complete": True,
                        }
                    )
                ]

                messages.append(
                    Message(
                        content=function_output,
                        role="function",
                        function_call={
                            "function_name": function_call.function_name,
                            "function_parameters": function_call.function_parameters,
                            "is_complete": True,
                        }
                    )
                )

                user_message = f"<function_output>\n{function_output}\n</function_output>\n\n{function_response}\n\n{format_message}"
            else:
                break
    
    def postprocessed_stream(*args, **kwargs):
        for messages in stream_state(*args, **kwargs):
            yield json.dumps([
                message.model_dump()
                for message in messages
            ]) + "\n"

    return StreamingResponse(postprocessed_stream(messages[-1].content + "\n\n" + format_message, snippets))

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
        new_snippets_string = "\n".join([
            relevant_snippet_template.format(
                i=i,
                file_path=snippet.file_path,
                content=snippet.content
            )
            for i, snippet in enumerate(new_snippets[NUM_SNIPPETS::-1]) if snippet.denotation not in fetched_snippet_denotations
        ])
        snippets += new_snippets[:NUM_SNIPPETS]
        return f"SUCCESS\n\nHere are the relevant files to your search request:\n{new_snippets_string}"
    else:
        return "ERROR\n\nTool not found."

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
