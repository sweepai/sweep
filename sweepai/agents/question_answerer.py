from copy import deepcopy
from sweepai.agents.modify import validate_and_parse_function_call
from sweepai.core.chat import ChatGPT
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo
from sweepai.utils.ticket_utils import prep_snippets

class QuestionAnswererException(Exception):
    def __init__(self, message):
        self.message = message

SNIPPET_FORMAT = """<snippet>
<file_name>{denotation}</file_name>
<source>
{contents}
</source>
</snippet>"""

tools_available = """You have access to the following tools to assist in fulfilling the user request:
<tool_description>
<tool_name>search_codebase</tool_name>
<description>
</description>
<parameters>
<parameter>
<name>question</name>
<type>str</type>
<description>
Detailed, specific natural language search question to search the codebase for relevant snippets. This should be in the form of a natural language question, like "What is the structure of the User model in the authentication module?"
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

<tool_description>
<tool_name>view_file</tool_name>
<description>
View the contents of a file in the codebase.
</description>
<parameters>
<parameter>
<name>file_path</name>
<type>str</type>
<description>
The path to the file you want to view.
</description>
</parameter>
</parameters>
</tool_description>

<tool_name>submit_task</tool_name>
<description>
Once you have collected and analyzed the relevant snippets, use this tool to submit the final response to the user's question.
</description>
<parameters>
<parameter>
<name>answer</name>
<type>str</type>
<description>
Provide a precise, detailed response to the user's question.
Be sure to copy and paste the relevant code snippets from the codebase into the response to explain implementations, usages and examples.
Make reference to entities in the codebase, and provide examples of usages and implementations whenever possible. 
When you mention an entity, be precise and clear by indicating the file they are from. For example, you may say: this functionality is accomplished by calling `foo.bar(x, y)` (from the `Foo` class in `src/modules/foo.py`). If you do not know where it is from, you need use the search_codebase tool to find it.
</description>
</parameter>
<parameter>
<name>sources</name>
<type>str</type>
<description>
Code files you referenced in your <answer>. Only include sources that are DIRECTLY REFERENCED in your answer, do not provide anything vaguely related. Keep this section MINIMAL. These must be full paths and not symlinks of aliases to files. Follow this format:
path/to/file.ext:a-b - justification and the section of the file that is relevant
path/to/other/file.ext:c-d - justification and the section of the file that is relevant
</description>
</parameter>
</parameters>
</tool_description>

<tool_name>raise_error</tool_name>
<description>
If the relevant information is not found in the codebase, use this tool to raise an error and provide a message to the user.
</description>
<parameters>
<parameter>
<name>message</name>
<type>str</type>
<description>
A summary of all the search queries you have tried and the information you have found so far.
</description>
</parameter>
</parameters>
</tool_description>"""

example_tool_calls = """Here are a list of illustrative examples of how to use the tools:

<examples>
To search the codebase for relevant snippets:

<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<question>Where are the push notification configurations and registration logic implemented using the Firebase Cloud Messaging library in the mobile app codebase?</question>
</parameters>
</invoke>
</function_call>

Notice that the `query` parameter is an extremely detailed, specific natural language search question.

<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<question>Where is the documentation that details how to configure the authentication module for the Stripe payments webhook? Is anything related to this detailed in docs/reference/stripe-configuration.mdx?</question>
<include_docs>true</include_docs>
</parameters>
</invoke>
</function_call>
</examples>

Notice that `include_docs` is set to true since we are retrieving documentation in this case. Also notice how the question is very specific, directed, with references to specific files or modules.

To submit the final response to the user's question:

<function_call>
<invoke>
<tool_name>submit_task</tool_name>
<parameters>
<answer>
The push notification configurations and registration logic using the Firebase Cloud Messaging library in the mobile app codebase are implemented in the `PushNotificationService` class in `src/services/push_notification_service.py`. The registration logic is implemented in the `register_device` method. Here is an example of how the registration logic is used in the `register_device` method.
</answer>
<sources>
src/services/push_notification_service.ts:10-20 - The `PushNotificationService` class that implements the push notification configurations and registration logic
src/services/push_notification_service.ts:30-40 - The `register_device` method that implements the registration logic
</sources>
</parameters>
</invoke>
</function_call>

The above are just illustrative examples and you should tailor your search queries to the specific user request.

Make sure to provide detailed, specific questions to search for relevant snippets in the codebase and only make one function call."""

search_agent_instructions = """You are an expert software developer tasked with finding relevant information in the codebase to resolve the user's request.

To complete the task, follow these steps:

1. Analyze the user's question to understand the information they are seeking.
2. Search the codebase for relevant code snippets that can help answer the question.
3. Provide a detailed response to the user's question based on the code snippets found.

In this environment, you have access to the following tools to assist in fulfilling the user request:

Use one tool at a time. Before every time you use a tool, think step-by-step in a <scratchpad> block about which tools you need to use and in what order to find the information needed to answer the user's question.

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
"""

search_agent_user_message = """Here is the user's question:

<request>
{question}
</request>

Now find the relevant code snippets in the codebase to answer the question. Use the `search_codebase` tool to search for snippets. Provide the query to search for relevant snippets in the codebase."""

"""
Don't know why but few-shot examples confuse Haiku.
"""

NO_TOOL_CALL_PROMPT = """FAILURE
Your last function call was incorrectly formatted.

Make sure you provide XML tags for function_call, invoke, tool_name and parameters for all function calls. Check the examples section for reference.

Resolve this error by following these steps:
1. In a scratchpad, list the tag name of each XML blocks of your last assistant message.
2. Based on the XML blocks and the contents, determine the last function call you we're trying to make.
3. Describe why your last function call was incorrectly formatted.
4. Finally, re-invoke your last function call with the corrected format, with the contents copied over."""

DEFAULT_FUNCTION_CALL = """<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<question>{question}</question>{flags}
</parameters>
</invoke>
</function_call>"""

DUPLICATE_QUESTION_MESSAGE = """You've already asked this question: {question}

Please ask a different question. If you can not find the answer in the search results, you need to ask more specific questions or ask questions about tangentially related topics. For example, if you find that a certain functionality is handled in another utilty module, you may need to search for that utility module to find the relevant information."""

SEARCH_RESULT_INSTRUCTIONS = """

First, think step-by-step in a scratchpad to analyze the search results and determine whether the answers provided here are sufficient or if there are additional relevant modules that we may need, such as referenced utility files, docs or tests.

Then, determine if the results are sufficient to answer the user's request:

<request>
{request}
<request>

Option A: Make additional search queries

If the search results are insufficient, you need to ask more specific questions or ask questions about tangentially related topics. For example, if you find that a certain functionality is handled in another utilty module, you may need to search for that utility module to find the relevant information. Keep in mind that you have already asked the following questions, so do not ask them again:

<previously_searched_queries>
{visited_questions}
</previously_searched_queries>

Instead, search for more specific, targetted search queries by analyzing the newly retrieved information. Think step-by-step to construct these better search queries.

Alternatively, if you have found a file that seems relevant but you would like to see the rest of the file, you can use the `view_file` tool to view the contents of the file.

Option B: Submit the task

Otherwise, if you have found all the relevant information to answer the user's request, submit the task using submit_task. If you submit, ensure that the <answer> includes relevant implementations, usages and examples of code wherever possible. Ensure that the <sources> section is MINIMAL and only includes all files you reference in your answer, and is correctly formatted, with each line contains a file path, start line, end line, and justification like in the example in the instructions.

Remember to use the valid function call format for either options."""

CORRECTED_SUBMIT_SOURCES_FORMAT = """ERROR

Invalid sources format. Please provide the sources in the following format, including a file path, start and end lines, and a justification, one per line, for each snippet referenced in your answer:

<sources>
path/to/file.ext:a-b - justification and the section of the file that is relevant
path/to/other/file.ext:c-d - justification and the section of the file that is relevant
</sources>"""

def search_codebase(
    question: str,
    cloned_repo: ClonedRepo,
    *args,
    **kwargs,
):
    rcm = prep_snippets(
        cloned_repo,
        question,
        use_multi_query=False,
        NUM_SNIPPETS_TO_KEEP=0,
        *args,
        **kwargs
    )
    rcm.current_top_snippets = [snippet for snippet in rcm.current_top_snippets][:5]
    return rcm

def rag(
    question: str,
    cloned_repo: ClonedRepo,
):

    # snippets_text = "\n\n".join([SNIPPET_FORMAT.format(
    #     denotation=snippet.denotation,
    #     contents=snippet.content,
    # ) for snippet in rcm.current_top_snippets[::-1]])

    chat_gpt = ChatGPT.from_system_message_string(
        prompt_string=search_agent_instructions + tools_available + "\n\n" + example_tool_calls,
    )

    user_message = search_agent_user_message.format(question=question)
    llm_state = {
        "visited_snippets": set(),
        "visited_questions": set(),
        "request": question,
    }

    for iter_num in range(10):
        if iter_num == 0:
            flags = ""
            if "test" in question:
                flags += "\n<include_tests>true</include_tests>"
            if "docs" in question or "documentation" in question:
                flags += "\n<include_docs>true</include_docs>"
            response = DEFAULT_FUNCTION_CALL.format(
                question=question,
                flags=flags,
            )
        else:
            response = chat_gpt.chat_anthropic(
                user_message,
                stop_sequences=["\n</function_call>"],
            ) + "</function_call>"

        function_call = validate_and_parse_function_call(
            response,
            chat_gpt
        )

        if function_call is None:
            # breakpoint()
            user_message = NO_TOOL_CALL_PROMPT.format(question=question, visited_questions="\n".join(sorted(list(llm_state["visited_questions"]))))
        else:
            function_call_response = handle_function_call(function_call, cloned_repo, llm_state)
            user_message = f"<function_output>\n{function_call_response}\n</function_output>"
        
        if "DONE" == function_call_response:
            return function_call.function_parameters.get("answer"), function_call.function_parameters.get("sources")
    raise QuestionAnswererException("Could not complete the task. The information may not exist in the codebase.")

def handle_function_call(function_call: AnthropicFunctionCall, cloned_repo: ClonedRepo, llm_state: dict):
    if function_call.function_name == "search_codebase":
        if "question" not in function_call.function_parameters:
            return "Please provide a question to search the codebase."
        question = function_call.function_parameters["question"].strip()
        include_docs = function_call.function_parameters.get("include_docs", "false") == "true"
        include_tests = function_call.function_parameters.get("include_tests", "false") == "true"
        previously_asked_question = deepcopy(llm_state["visited_questions"])
        if not question.strip():
            return "Question cannot be empty. Please provide a detailed, specific natural language search question to search the codebase for relevant snippets."
        if question in llm_state["visited_questions"] and not include_docs and not include_tests:
            # breakpoint()
            return DUPLICATE_QUESTION_MESSAGE.format(question=question)
        llm_state["visited_questions"].add(question)
        rcm = search_codebase(
            question=question,
            cloned_repo=cloned_repo,
            include_docs=include_docs,
            include_tests=include_tests,
        )
        snippets = []
        prev_visited_snippets = deepcopy(llm_state["visited_snippets"])
        for snippet in rcm.current_top_snippets[::-1]:
            if snippet.denotation not in llm_state["visited_snippets"]:
                expand_size = 100
                snippets.append(SNIPPET_FORMAT.format(
                    denotation=snippet.expand(expand_size).denotation,
                    contents=snippet.expand(expand_size).get_snippet(add_lines=False),
                ))
                llm_state["visited_snippets"].add(snippet.denotation)
            else:
                snippets.append(f"Snippet already retrieved previously: {snippet.denotation}")
        snippets_string = "\n\n".join(snippets)
        snippets_string += f"\n\nYour last search query was \"{question}\". Here is a list of all the files retrieved in this search query:\n" + "\n".join([f"- {snippet.denotation}" for snippet in rcm.current_top_snippets])
        if prev_visited_snippets:
            snippets_string += "\n\nHere is a list of all the files retrieved previously:\n" + "\n".join([f"- {snippet}" for snippet in sorted(list(prev_visited_snippets))])
        snippets_string += f"\n\nThe above are the snippets that are found in decreasing order of relevance to the search query \"{function_call.function_parameters.get('question')}\"."
        if previously_asked_question:
            snippets_string += f"\n\nYou have already asked the following questions so do not ask them again:\n" + "\n".join([f"- {question}" for question in previously_asked_question])
        warning_messages = ""
        if "test" in question and not include_tests:
            warning_messages += "\n\nWARNING\n\nThe search query contains the word 'test'. You may need to toggle the include_tests flag to find relevant information."
        if ("docs" in question or "documentation" in question) and not include_docs:
            warning_messages += "\n\nWARNING\n\nThe search query contains the word 'doc'. You may need to toggle the include_docs flag to find relevant information."
        return snippets_string + SEARCH_RESULT_INSTRUCTIONS.format(
            request=llm_state["request"],
            visited_questions="\n".join(sorted(list(llm_state["visited_questions"])))
        ) + warning_messages
    if function_call.function_name == "submit_task":
        for key in ("answer", "sources"):
            if key not in function_call.function_parameters:
                return f"Please provide a {key} parameter to submit the task. You must provide an analysis, answer, and sources to submit the task as three separate parameters."

        error_message = ""
        sources = function_call.function_parameters["sources"]
        for line in sources.splitlines():
            if not line.strip():
                continue
            if " - " not in line:
                error_message = CORRECTED_SUBMIT_SOURCES_FORMAT + f"\n\nThe following line is missing the ' - ' delimiter before the justification block:\n\n{line}"
                break
            snippet_denotation  = line.split(" - ")[0]
            if ":" not in snippet_denotation:
                error_message = CORRECTED_SUBMIT_SOURCES_FORMAT + f"\n\nSnippet denotations must be in the format 'path/to/file.ext:a-b', containing the file path and line numbers deliminated by a ':'. The following line is missing the ':' delimiter:\n\n{line}"
                break
            file_path, line_numbers = snippet_denotation.split(":")
            line_numbers, *_ = line_numbers.split(",")
            if "-" not in line_numbers:
                error_message = CORRECTED_SUBMIT_SOURCES_FORMAT + f"\n\nSnippet denotations must be in the format 'path/to/file.ext:a-b', and the line numbers must include a start and end line deliminated by a '-'. The following line is missing the '-' delimiter in the line numbers:\n\n{line}"
                break
            start_line, end_line = line_numbers.split("-")
            try:
                cloned_repo.get_file_contents(file_path)
            except FileNotFoundError:
                error_message = f"ERROR\n\nThe file path '{file_path}' does not exist in the codebase. Please provide a valid file path."
                break
        if error_message:
            return error_message
        else:
            return "DONE"
    elif function_call.function_name == "view_file":
        file_contents = cloned_repo.get_file_contents(function_call.function_parameters["file_path"])
        num_lines = len(file_contents.splitlines())
        return f"Here are the contents:\n\n```\n{file_contents}\n```\n\nHere is how you can denote this snippet for listing it in the sources: {function_call.function_parameters['file_path']}:0-{num_lines-1}"
    elif function_call.function_name == "raise_error":
        if "message" not in function_call.function_parameters:
            return "Please provide a message to raise an error."
        raise QuestionAnswererException(function_call.function_parameters["message"])
    else:
        return "ERROR\n\nInvalid tool name."

if __name__ == "__main__":
    cloned_repo = MockClonedRepo(
        _repo_dir = "/tmp/sweep",
        repo_full_name="sweepai/sweep",
        # _repo_dir = "/mnt/volume_sfo3_03/django__django-10213",
        # repo_full_name="django/django",
    )
    rag(
        question="What version of django are we using in the codebase?",
        # question="Where in the Django codebase are the unit tests located for the management commands, specifically those related to testing the BaseCommand class functionality?",
        cloned_repo=cloned_repo,
    )