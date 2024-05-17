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

You MUST follow the following XML-based format:

### Format

Use GitHub-styled markdown for your responses. You must respond with the following three distinct sections:

# 1. Summary and analysis
<user_response>
## Summary
First, list and summarize each NEW file from the codebase provided from the last function output that is relevant to the user's question. You may not need to summarize all provided files.

## New information
Secondly, list all new information that was retrieved from the codebase that is relevant to the user's question, especially if it invalidates any previous beliefs or assumptions.

Determine if you have sufficient information to answer the user's question. If not, determine the information you need to answer the question completely by making `search_codebase` tool calls.
</analysis>

# 2. User Response

<user_response>
Determine if you have sufficient information to answer the user's question. If not, determine the information you need to answer the question completely by making `search_codebase` tool calls.

If so, rewrite your previous response with the new information and any invalidated beliefs or assumptions. Make sure this answer is complete and helpful. Provide code examples, explanations and excerpts wherever possible to provide concrete explanations. When explaining how to add new code, always write out the new code. When suggesting code changes, write out all the code changes required in the unified diff format.
</user_response>

# 3. Self-Critique

<self_critique>
Then, self-critique your answer and validate that you have completely answered the user's question. If the user's answer is relatively broad, you are done.

Otherwise, if the user's question is specific, and asks to implement a feature or fix a bug, determine what additional information you need to answer the user's question. Specifically, validate that all interfaces are being used correctly based on the contents of the retrieved files -- if you cannot verify this, then you must find the relevant information such as the correct interface or schema to validate the usage. If you need to search the codebase for more information, such as for how a particular feature in the codebase works, use the `search_codebase` tool in the next section.
</self_critique>

# 4. Function Calls (Optional)

Then, make each function call like so:
<function_calls>
[the list of function calls go here, using the valid XML format for function calls]
</function_calls>""" + example_tool_calls

format_message = """You MUST follow the following XML-based format:

### Format

Use GitHub-styled markdown for your responses. You must respond with the following three distinct sections:

# 1. Summary and analysis
<analysis>
First, list and summarize each file from the codebase provided that is relevant to the user's question. You may not need to summarize all provided files.

Then, determine if you have sufficient information to answer the user's question. If not, determine the information you need to answer the question completely by making `search_codebase` tool calls.
</analysis>

# 2. User Response

<user_response>
Write a complete helpful response to the user's question in full detail. Make sure this answer is complete and helpful. Provide code examples, explanations and excerpts wherever possible to provide concrete explanations. When explaining how to add new code, always write out the new code. When suggesting code changes, write out all the code changes required in the unified diff format.
</user_response>

# 3. Self-Critique

<self_critique>
Then, self-critique your answer and validate that you have completely answered the user's question. If the user's answer is relatively broad, you are done.

Otherwise, if the user's question is specific, and asks to implement a feature or fix a bug, determine what additional information you need to answer the user's question. Specifically, validate that all interfaces are being used correctly based on the contents of the retrieved files -- if you cannot verify this, then you must find the relevant information such as the correct interface or schema to validate the usage. If you need to search the codebase for more information, such as for how a particular feature in the codebase works, use the `search_codebase` tool in the next section.
</self_critique>

# 4. Function Calls (Optional)

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