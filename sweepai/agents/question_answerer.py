from copy import deepcopy
import re
import subprocess

from loguru import logger
from sweepai.agents.agent_utils import Parameter, get_function_call, tool
from sweepai.core.chat import ChatGPT
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo
from sweepai.utils.ticket_utils import prep_snippets
from sweepai.core.entities import SNIPPET_FORMAT, Snippet

class QuestionAnswererException(Exception):
    def __init__(self, message):
        self.message = message

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

def search_codebase(
    question: str,
    cloned_repo: ClonedRepo,
    k=5,
    *args,
    **kwargs,
):
    snippets = prep_snippets(
        cloned_repo,
        question,
        use_multi_query=False,
        NUM_SNIPPETS_TO_KEEP=0,
        skip_analyze_agent=True,
        *args,
        **kwargs
    )
    return snippets[:k]

@tool()
def semantic_search(
    question: Parameter("A single, detailed, specific natural language search question to search the codebase for relevant snippets."),
    cloned_repo: ClonedRepo,
    llm_state: dict,
):
    previously_asked_question = deepcopy(llm_state["visited_questions"])
    if not question.strip():
        return "Question cannot be empty. Please provide a detailed, specific natural language search question to search the codebase for relevant snippets."
    if question in llm_state["visited_questions"]:
        return DUPLICATE_QUESTION_MESSAGE.format(question=question)
    llm_state["visited_questions"].add(question)
    retrieved_snippets = search_codebase(
        question=question,
        cloned_repo=cloned_repo,
    )
    snippets = []
    prev_visited_snippets = deepcopy(llm_state["visited_snippets"])
    for snippet in retrieved_snippets[::-1]:
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
    snippets_string += f"\n\nYour last search query was \"{question}\". Here is a list of all the files retrieved in this search query:\n" + "\n".join([f"- {snippet.denotation}" for snippet in retrieved_snippets])
    if prev_visited_snippets:
        snippets_string += "\n\nHere is a list of all the files retrieved previously:\n" + "\n".join([f"- {snippet}" for snippet in sorted(list(prev_visited_snippets))])
    snippets_string += f"\n\nThe above are the snippets that are found in decreasing order of relevance to the search query \"{question}\"."
    if previously_asked_question:
        snippets_string += "\n\nYou have already asked the following questions so do not ask them again:\n" + "\n".join([f"- {question}" for question in previously_asked_question])
    warning_messages = ""
    return snippets_string + SEARCH_RESULT_INSTRUCTIONS.format(
        request=llm_state["request"],
        visited_questions="\n".join(sorted(list(llm_state["visited_questions"])))
    ) + warning_messages

RIPGREP_SEARCH_RESULT_INSTRUCTIONS = """

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

def post_filter_ripgrep_results(
    results: str,
    max_line_length: int = 300,
):
    output = ""
    for line in results.splitlines():
        if len(line) < 300:
            output += line + "\n"
        else:
            output += line[:300] + f"... (omitted {len(line) - 300} characters)\n"
    return output.strip("\n")

@tool()
def ripgrep(
    query: Parameter("The keyword to search for in the codebase."),
    cloned_repo: ClonedRepo,
    llm_state: dict,
):
    """
    Search for a keyword in the codebase.
    """
    response = subprocess.run(
        " ".join([
            "rg",
            "-n",
            # "-w",
            "-i",
            "-C=5",
            "--heading",
            "--sort-files",
            query,
        ]),
        shell=True,
        capture_output=True,
        text=True,
        cwd=cloned_repo.repo_dir,
    )
    if response.returncode != 0:
        if not response.stderr:
            return f"No results found for '{query}' in the codebase."
        else:
            return f"Error running ripgrep:\n\n{response.stderr}"
    results = post_filter_ripgrep_results(response.stdout)
    return f"Here are ALL occurrences of '{query}' in the codebase:\n\n```{results}```\n" + RIPGREP_SEARCH_RESULT_INSTRUCTIONS.format(
        request=llm_state["request"],
        visited_questions="\n".join(sorted(list(llm_state["visited_questions"])))
    )

@tool()
def view_file(
    justification: Parameter("Justification for why you want to view this file."),
    file_path: Parameter("The path to the file you want to view."),
    cloned_repo: ClonedRepo,
):
    try:
        file_contents = cloned_repo.get_file_contents(file_path)
    except FileNotFoundError as e:
        logger.error(f"Could not find file {file_path} view_file:\n{e}")
        return f"The file {file_path} doesn't exist in this repo, make sure the file path provided is correct."
    except Exception as e:
        logger.error(f"Error calling view_file:\n{e}")
        raise e
    num_lines = len(file_contents.splitlines())
    return f"Here are the contents:\n\n```\n{file_contents}\n```\n\nHere is how you can denote this snippet for listing it in the sources: {file_path}:0-{num_lines-1}"

CORRECTED_SUBMIT_SOURCES_FORMAT = """ERROR

Invalid sources format. Please provide the sources in the following format, including a file path, start and end lines, and a justification, one per line, for each snippet referenced in your answer:

<sources>
<source>
<file_path>
file_path
</file_path>
<start_line>
start_line
</start_line>
<end_line>
end_line
</end_line>
<justification>
justification and the section of the file that is relevant
</justification>
</source>
[additional sources...]
</sources>"""


def parse_sources(sources: str, cloned_repo: ClonedRepo):
    source_pattern = re.compile(r"<source>\s+<file_path>(?P<file_path>.*?)</file_path>\s+<start_line>(?P<start_line>\d+?)</start_line>\s+<end_line>(?P<end_line>\d+?)</end_line>\s+<justification>(?P<justification>.*?)</justification>\s+</source>", re.DOTALL)
    source_matches = source_pattern.finditer(sources)
    snippets = []
    for source in source_matches:
        file_path = source.group("file_path")
        start_line = source.group("start_line")
        end_line = source.group("end_line")
        justification = source.group("justification")
        try:
            content = cloned_repo.get_file_contents(file_path)
        except FileNotFoundError:
            similar_files = cloned_repo.get_similar_file_paths(file_path)
            if similar_files:
                raise Exception(f"ERROR\n\nThe file path '{file_path}' does not exist in the codebase. Did you mean: {similar_files}?")
            else:
                raise Exception(f"ERROR\n\nThe file path '{file_path}' does not exist in the codebase. Please provide a valid file path.")
        snippets.append(Snippet(
            content=content,
            start=int(start_line),
            end=max(int(start_line) + 1, int(end_line)),
            file_path=file_path,
        ))
        if not file_path or not start_line or not end_line or not justification:
            raise Exception(CORRECTED_SUBMIT_SOURCES_FORMAT + f"\n\nThe following source is missing one of the required fields:\n\n{source.group(0)}")
    return snippets

@tool()
def submit_task(
    answer: Parameter("The answer to the user's question."),
    sources: Parameter("The sources of the answer."),
    cloned_repo: ClonedRepo,
    justification: str = "", # breaks without this line
):
    """
    Once you have collected and analyzed the relevant snippets, use this tool to submit the final response to the user's question.
    """
    error_message = ""
    try:
        parse_sources(sources, cloned_repo)
    except Exception as e:
        return str(e)
    if error_message:
        return error_message
    else:
        return "DONE"

tools = [semantic_search, ripgrep, view_file, submit_task]

tools_available = """You have access to the following tools to assist in fulfilling the user request:

""" + "\n\n".join(tool.get_xml() for tool in tools)

example_tool_calls = """Here are a list of illustrative examples of how to use the tools:

<examples>
To search the codebase for relevant snippets:

<function_call>
<semantic_search>
<question>
Where are the push notification configurations and registration logic implemented using in the mobile app codebase?
</question>
</semantic_search>
</function_call>

Notice that the `query` parameter is a single, detailed, specific natural language search question. Be sure to ask only one question.

To search for a keyword:

<function_call>
<ripgrep>
<query>
push_notification
</query>
</ripgrep>
</function_call>

This will return all lines of code in the codebase that contain the keyword "push_notification". This is great for finding all usages of a certain function, class, or constant.

To submit the final response to the user's question:

<function_call>
<submit_task>
<answer>
The push notification configurations and registration logic using the Firebase Cloud Messaging library in the mobile app codebase are implemented in the `PushNotificationService` class in `src/services/push_notification_service.py`. The registration logic is implemented in the `register_device` method. Here is an example of how the registration logic is used in the `register_device` method.
</answer>
<sources>
<source>
<file_path>
src/services/push_notification_service.ts
</file_path>
<start_line>
10
</start_line>
<end_line>
20
</end_line>
<justification>
The `PushNotificationService` class that implements the push notification configurations and registration logic
</justification>
</source>
<source>
<file_path>
src/services/push_notification_service.ts
</file_path>
<start_line>
30
</start_line>
<end_line>
40
</end_line>
<justification>
The `register_device` method that implements the registration logic
</justification>
</source>
</sources>
</submit_task>
</function_call>

The above are just illustrative examples and you should tailor your search queries to the specific user request.

Make sure to provide detailed, specific questions to search for relevant snippets in the codebase and only make one function call."""

search_agent_instructions = """You are an expert software developer tasked with finding relevant information in the codebase to resolve the user's request.

To complete the task, follow these steps:

1. Analyze the user's question to understand the information they are seeking.
2. Search the codebase for relevant code snippets that can help answer the question using the semantic_search and ripgrep tools.
3. Provide a detailed response to the user's question based on the code snippets found.

In this environment, you have access to the following tools to assist in fulfilling the user request:

Use one tool at a time. Before every time you use a tool, think step-by-step in a <scratchpad> block about which tools you need to use and in what order to find the information needed to answer the user's question.

Once you have collected and analyzed the relevant snippets, use the `submit_task` tool to submit the final response to the user's question.

You MUST call them like this:
<function_call>
<tool_name>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</tool_name>
</function_call>

Here are the tools available:
"""

search_agent_user_message = """Here is the user's question:

<request>
{question}
</request>

Now find the relevant code snippets in the codebase to answer the question. Use the `semantic_search` and `ripgrep` tools to search for snippets. Provide the query to search for relevant snippets in the codebase."""

"""
Don't know why but few-shot examples confuse Haiku.
"""

NO_TOOL_CALL_PROMPT = """FAILURE
Your last function call was incorrectly formatted.

Make sure you provide XML tags for function_call, tool_name and parameters for all function calls. Check the examples section for reference.

Resolve this error by following these steps:
1. In a scratchpad, list the tag name of each XML blocks of your last assistant message.
2. Based on the XML blocks and the contents, determine the last function call you we're trying to make.
3. Describe why your last function call was incorrectly formatted.
4. Finally, re-invoke your last function call with the corrected format, with the contents copied over.

Here are the available tools: """ + " ".join([tool.name for tool in tools]) + '.'

DEFAULT_FUNCTION_CALL = """<function_call>
<semantic_search>
<question>{question}</question>
</semantic_search>
</function_call>"""


def rag(
    question: str,
    cloned_repo: ClonedRepo,
):
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
        function_call_response, function_call = get_function_call(
            chat_gpt,
            user_message,
            tools,
            llm_kwargs={
                "use_openai": True,
            },
            cloned_repo=cloned_repo,
            llm_state=llm_state,
        )

        user_message = f"<function_call>\n{function_call_response}\n</function_call>"
        
        if function_call_response == "DONE":
            return function_call.function_parameters.get("answer"), function_call.function_parameters.get("sources")
    raise QuestionAnswererException("Could not complete the task. The information may not exist in the codebase.")

if __name__ == "__main__":
    cloned_repo = MockClonedRepo(
        _repo_dir = "/tmp/sweep",
        repo_full_name="sweepai/sweep",
    )
    rag(
        question="What version of django is used in this codebase?",
        cloned_repo=cloned_repo,
    )
