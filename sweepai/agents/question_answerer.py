from copy import deepcopy
from sweepai.agents.modify import validate_and_parse_function_call
from sweepai.core.chat import ChatGPT
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo
from sweepai.utils.ticket_utils import prep_snippets

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
</tool_description>"""

example_tool_calls = """Here are examples of how to use the tools:

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

Notice that `include_docs` is set to true since we are retrieving documentation in this case. Also notice how the question is very specific, directed, with references to specific files or modules.

The above are just illustrative examples. Make sure to provide detailed, specific questions to search for relevant snippets in the codebase and only make one function call."""

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

NO_TOOL_CALL_PROMPT = """FAILURE
Your last function call was incorrectly formatted. Here is are examples of correct function calls:

For example, to search the codebase for relevant snippets:

<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<question>How is the User model defined in the authentication module for the Stripe payements webhook?</question>
</parameters>
</invoke>
</function_call>

If you have sufficient sources to answer the question, call the submit_task function with an extremely detailed, well-referenced response in the following format:

<function_call>
<invoke>
<tool_name>submit_task</tool_name>
<parameters>
<answer>
Provide a detailed response to the user's question.

Reference all relevant entities in the codebase, and provide examples of usages and implementations whenever possible. 

When you mention an entity, be precise and clear by indicating the file they are from. For example, you may say: this functionality is accomplished by calling `foo.bar(x, y)` (from the `Foo` class in `src/modules/foo.py`).
</answer>
<sources>
Code files you referenced in your <answer>. Only include sources that are DIRECTLY REFERENCED in your answer, do not provide anything vaguely related. Keep this section MINIMAL. These must be full paths and not symlinks of aliases to files. Follow this format:
path/to/file.ext:a-b - justification and the section of the file that is relevant
path/to/other/file.ext:c-d - justification and the section of the file that is relevant
</sources>
</parameters>
</invoke>
</function_call>

First, in a scratchpad, think step-by-step to analyze the search results and determine whether the source results retrieved so far are sufficient. Also determine why your last function call weas incorrectly formatted. Then, you may make additional search queries using search_codebase or submit the task using submit_task."""

DEFAULT_FUNCTION_CALL = """<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<question>{question}</question>
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

If the search results are insufficient, you need to ask more specific questions or ask questions about tangentially related topics. For example, if you find that a certain functionality is handled in another utilty module, you may need to search for that utility module to find the relevant information.

Otherwise, if you have found all the relevant information to answer the user's request, submit the task using submit_task. If you submit, ensure that the <answer> includes relevant implementations, usages and examples of code wherever possible. Ensure that the <sources> section is MINIMAL and only includes all files you reference in your answer, and is correctly formatted, with each line contains a file path, start line, end line, and justification. Be sure to use the valid function call format."""

CORRECTED_SUBMIT_SOURCES_FORMAT = """ERROR

Invalid sources format. Please provide the sources in the following format, including a file path, start and end lines, and a justification for each snippet referenced in your answer:

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
            response = DEFAULT_FUNCTION_CALL.format(question=question)
        else:
            response = chat_gpt.chat_anthropic(
                user_message,
                stop_sequences=["</function_call>"],
            ) + "</function_call>"

        function_call = validate_and_parse_function_call(
            response,
            chat_gpt
        )

        if function_call is None:
            user_message = NO_TOOL_CALL_PROMPT
        else:
            function_call_response = handle_function_call(function_call, cloned_repo, llm_state)
            user_message = f"<function_output>\n{function_call_response}\n</function_output>"
        
        if "DONE" == function_call_response:
            return function_call.function_parameters.get("answer"), function_call.function_parameters.get("sources")
    raise ValueError("Could not complete the task.")

def handle_function_call(function_call: AnthropicFunctionCall, cloned_repo: ClonedRepo, llm_state: dict):
    if function_call.function_name == "search_codebase":
        if "question" not in function_call.function_parameters:
            return "Please provide a question to search the codebase."
        question = function_call.function_parameters["question"].strip()
        previously_asked_question = deepcopy(llm_state["visited_questions"])
        if not question.strip():
            return "Question cannot be empty. Please provide a detailed, specific natural language search question to search the codebase for relevant snippets."
        if question in llm_state["visited_questions"]:
            return DUPLICATE_QUESTION_MESSAGE.format(question=question)
        llm_state["visited_questions"].add(question)
        rcm = search_codebase(
            question=question,
            cloned_repo=cloned_repo,
            include_docs=function_call.function_parameters.get("include_docs", "false") == "true",
            include_tests=function_call.function_parameters.get("include_tests", "false") == "true",
        )
        snippets = []
        prev_visited_snippets = deepcopy(llm_state["visited_snippets"])
        for snippet in rcm.current_top_snippets[::-1]:
            if snippet.denotation not in llm_state["visited_snippets"]:
                snippets.append(SNIPPET_FORMAT.format(
                    denotation=snippet.denotation,
                    contents=snippet.get_snippet(add_lines=False),
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
        return snippets_string + SEARCH_RESULT_INSTRUCTIONS.format(request=llm_state["request"])
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
                error_message = CORRECTED_SUBMIT_SOURCES_FORMAT + "\n\nYour sources are missing the ' - ' delimiter before the justification block."
                break
            snippet_denotation  = line.split(" - ")[0]
            if ":" not in snippet_denotation:
                error_message = CORRECTED_SUBMIT_SOURCES_FORMAT + "\n\nSnippet denotations must be in the format 'path/to/file.ext:a-b', containing the file path and line numbers deliminated by a ':'."
                break
            file_path, line_numbers = snippet_denotation.split(":")
            if "-" not in line_numbers:
                error_message = CORRECTED_SUBMIT_SOURCES_FORMAT + "\n\nSnippet denotations must be in the format 'path/to/file.ext:a-b', and the line numbers must include a start and end line deliminated by a '-'."
                break
            start_line, end_line = line_numbers.split("-")
            try:
                cloned_repo.get_file_contents(file_path)
            except FileNotFoundError:
                error_message = f"ERROR\n\nThe file path '{file_path}' does not exist in the codebase."
                break
        if error_message:
            return error_message
        else:
            return "DONE"
    else:
        return "ERROR\n\nInvalid tool name."

if __name__ == "__main__":
    cloned_repo = MockClonedRepo(
        _repo_dir = "/tmp/sweep",
        repo_full_name="sweepai/sweep",
    )
    rag(
        question="What version of tree-sitter are we using?",
        cloned_repo=cloned_repo,
    )