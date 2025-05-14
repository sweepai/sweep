from copy import deepcopy
import re
import subprocess

from loguru import logger
from sweepai.agents.agent_utils import Parameter, get_function_call, tool
from sweepai.core.chat import ChatGPT
from sweepai.core.snippet_utils import merge_snippet_ranges
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo
from sweepai.utils.ticket_utils import prep_snippets
from sweepai.core.entities import SNIPPET_FORMAT, Snippet

class QuestionAnswererException(Exception):
    def __init__(self, message):
        self.message = message


file_search_agent_dependency_tree_initialisation = """
You must also build and maintain a dependency tree of all code entities that you are working with.
Begin by identifying the main entity that you are working with when resolving the user's request. 
Now you must identify all relevant dependencies that this entity relies on and all entities that rely on this entity. For example, if the code entity is a function you must find out all files where this function is called. You must also examine the contents of this function to determine if it calls any functions or has uses any variables that are defined in other files.
If at any point you discover an entity that is not located in the current code files that you have access to, you are to use the vector search tool or rip grep tool to search for the file where the unknown entity is located. 
You must also indicate the types for each code entity in the dependency tree you are working with. 
Include it with the entity you are referencing, if not, you must find the relevant file that has the type definition for the code entity.
Any file within this dependency tree that you build must be added to the context using the `add_files_to_context` tool.
Respond in the following format:
<dependency_tree>
[dependency tree here]
Example:
main_code_entity:
    my_function (python function) -> path/to/filea.py
internal_entities:
    relevant_external_var_used_in_my_function (var_type) -> path/to/external_var_def.py
    relevant_other_function_called_in_my_function (python function) -> path/to/other_function_def.py
    relevant_second_external_var_used_in_my_function (unknown type) -> unknown file
external_entities:
    function_calls_my_function_in_other_file (python function) -> path/to/other_file.py
In this example another search would be required to figure out the type of relevant_second_external_var_used_in_my_function and the file it belongs to. Usually this can be done by examining the imports of the file.
Notice that all entities are one step away from the main code entity. All files mentioned in the dependency tree would need to be added to context using the `add_files_to_context` tool.
</dependency_tree>

Your job is not done until you finish building this dependency tree by including all relevant entities and definitions to the user request.
The whole point of this dependency tree is to aid you in figuring out when you can stop searching for files and when you have found all the relevant files that you need to solve the user request.
"""

file_search_agent_dependency_tree_update = """
You must also update the dependency tree with the new code entity that you have discovered. 
Then check if there are still any missing types or files that you need to find.

Remember to respond in the following format:
<dependency_tree>
[dependency tree here]
</dependency_tree>

Remember to add all files that you have found to the context using the `add_files_to_context` tool.
"""

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

If you have exhausted all search options and still have not found the answer, you can submit an answer with everything you've searched for and found, clarifying that you can not find the answer.

Remember to use the valid function call format for either options."""

SEARCH_RESULT_INSTRUCTIONS_FILE_SEARCHER = """

First, think step-by-step in a scratchpad to analyze the search results and determine whether the answers provided here are sufficient or if there are additional relevant code files that we may need, such as referenced utility files, docs or tests.

Then, determine if the results are sufficient to answer the user's request:

<user_request>
{request}
<user_request>

Option A: Make additional search queries

If these files are not sufficient, you need to ask more specific questions or ask questions about tangentially related topics. For example, if you find that a certain functionality is handled in another utilty module, you may need to search for that utility module to find the relevant information. Keep in mind that you have already asked the following questions, so do not ask them again:

<previously_searched_queries>
{visited_questions}
</previously_searched_queries>

Instead, search for more specific, targetted search queries by analyzing the newly retrieved information. Think step-by-step to construct these better search queries.

Alternatively, if you have found a file that seems relevant but you would like to see the rest of the file, you can use the `view_file` tool to view the contents of the file.

Option B: Submit the relevant files

Otherwise, if you have found all the relevant information to answer the user's request, submit the files using `add_files_to_context`. 

If you have exhausted all search options and still have not found the answer, submit all the relevant files that you have found using `add_files_to_context` and then call `done_file_search` to indicate that you are finished.
""" + file_search_agent_dependency_tree_update

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

@tool()
def vector_search(
    question: Parameter("A single, detailed, specific natural language search question to search the codebase for relevant code snippets."),
    cloned_repo: ClonedRepo,
    llm_state: dict,
):
    previously_asked_question = deepcopy(llm_state["visited_questions"])
    if not question.strip():
        return "Question cannot be empty. Please provide a detailed, specific natural language search question to search the codebase for relevant code snippets."
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
    return snippets_string + SEARCH_RESULT_INSTRUCTIONS_FILE_SEARCHER.format(
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

FILE_NOT_FOUND_ERROR = """ERROR

The following files do not exist in the codebase:
{file_paths}

Solve this by following these steps:
1. Think about what the correct file is in <scratchpad></scratchpad> XML tags.
2. Make the submit function call again with the corrected file path in <function_call></function_call> XML tags. You must also include the <plan></plan>, <explanation></explanation> and <sources></sources> XML tags.

YOU WILL USE THE XML TAGS. Otherwise, the assistant will not be able to parse the answer."""


def parse_sources(sources: str, cloned_repo: ClonedRepo):
    source_pattern = re.compile(r"<source>\s+<file_path>(?P<file_path>.*?)</file_path>\s+<start_line>(?P<start_line>\d+?)</start_line>\s+<end_line>(?P<end_line>\d+?)</end_line>\s+(<justification>(?P<justification>.*?)</justification>\s+)?</source>", re.DOTALL)
    source_matches = source_pattern.finditer(sources)
    snippets = []
    missing_files = []
    for source in source_matches:
        file_path = source.group("file_path")
        start_line = source.group("start_line")
        end_line = source.group("end_line")
        try:
            content = cloned_repo.get_file_contents(file_path)
        except FileNotFoundError:
            missing_files.append(file_path)
        snippets.append(Snippet(
            content=content,
            start=int(start_line),
            end=max(int(start_line) + 1, int(end_line)),
            file_path=file_path,
        ))
        if not file_path or not start_line or not end_line:
            raise Exception(CORRECTED_SUBMIT_SOURCES_FORMAT + f"\n\nThe following source is missing one of the required fields:\n\n{source.group(0)}")
    if missing_files:
        raise Exception(FILE_NOT_FOUND_ERROR.format(file_paths="\n".join(missing_files)))
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

@tool()
def add_files_to_context(
    file_names: Parameter("The full paths of the files you want to add to context. Ensure correct spelling and capitalization. Separate multiple files with a comma."),
    cloned_repo: ClonedRepo,
    relevant_files: list[Snippet],
    llm_state: dict,
):
    """
Use this tool to indicate the files that you believe are needed in order to fully resolve the user request. 
You can add a portion of a file using the following format: file_path:start_line-end_line
Not including a start_line and end_line will add the entire file to context.
Files are indexed from 0.

Here is an example:

<function_call>
<add_files_to_context>
<file_names>
path/to/filea.py:0-123, path/to/fileb.py, path/to/filec.py:34-345
</file_names>
</add_files_to_context>
</function_call>
    """
    error_message = ""

    file_names = file_names.split(",")
    file_names: list[str] = [file_name.strip() for file_name in file_names]
    existing_files = set([snippet.file_path for snippet in relevant_files])
    bad_files = []
    for file_to_add in file_names:
        file_range: list[int] = []
        if ":" in file_to_add:
            file_name, file_range = file_name.split(":")
            file_range = [int(num) for num in file_range.split("-")]
        file_name = file_to_add
        # make sure the file exists in the cloned_repo
        file_contents = ""
        try:
            file_contents = cloned_repo.get_file_contents(file_name)
        except FileNotFoundError:
            bad_files.append(file_name)
            continue
            
        if file_contents:
            file_lines = file_contents.splitlines()
        else:
            file_lines = [""]
        file_length = len(file_lines)
        # if file name is already in context than make sure ranges dont overlap and if they do merge them
        if file_name in existing_files:
            if file_range:
                # all snippet ranges
                all_ranges = []
                snippet_indexes = []
                for i, snippet in enumerate(relevant_files):
                    if snippet.file_path == file_name:
                        all_ranges.append((snippet.start, snippet.end))
                        snippet_indexes.append(i)
                all_ranges.append(file_range)
                # check if the new range overlaps with any of the existing ranges and merge them
                new_ranges = merge_snippet_ranges(all_ranges)
                # remove and recreate the snippets
                for i in snippet_indexes[::-1]:
                    relevant_files.pop(i)
                for start, end in new_ranges:
                    relevant_files.append(Snippet(
                        content=file_contents,
                        start=start,
                        end=end,
                        file_path=file_name,
                    ))
            # adding whole file so we just overwrite the entire file
            else:
                snippet_indexes = []
                first_occurence = True
                for i, snippet in enumerate(relevant_files):
                    if snippet.file_path == file_name:
                        if first_occurence:
                            snippet.start = 0
                            snippet.end = file_length
                            first_occurence = False
                        else:
                            snippet_indexes.append(i)
                # now that the snippet is the whole file there is no need for the other snippets
                # iterate backwards through relevant files and pop the indexes
                for i in snippet_indexes[::-1]:
                    relevant_files.pop(i)
        else: # otherwise we add the snippet
            start = 0
            end = file_length
            if file_range:
                start, end = file_range
            relevant_files.append(Snippet(
                content=file_contents,
                start=0,
                end=file_length,
                file_path=file_name,
            ))
    relevant_snippets = f'{", ".join([f"{snippet.file_path}:{snippet.start}-{snippet.end}" for snippet in relevant_files])}'
    if bad_files:
        if len(bad_files) == 1:
            error_message += f"The file {bad_files[0]} does not exist in the codebase and was not added as. Please ensure the correct spelling and capitalization of the file name and call the `add_file_to_context` tool again."
        else:
            error_message += f"The following files do not exist in the codebase: {', '.join(bad_files)}. Please ensure the correct spelling and capitalization of the file names and call the `add_file_to_context` tool again."
        error_message += f" The current files in context are {relevant_snippets}."
        return error_message
    return f'The current files you have identified as being relevant are {relevant_snippets}. You may move on to finding the next files that are relevant. If these were the final files you wanted to add, call the `done_file_search` tool to indicate that you are finished.'

@tool()
def done_file_search(
    reason: Parameter("Justification for why you are calling this tool and why you have found all relevant files."),
    justification: str = "", # breaks without this line
):
    """
    Once you are confident you have found and added ALL relevant files to context you may call this tool to indicate that you are finished.
    """
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

example_tool_calls_file_searcher = """Here are a list of illustrative examples of how to use the tools:

<examples>
To search the codebase for relevant snippets:

<function_call>
<vector_search>
<question>
Where are the push notification configurations and registration logic implemented using in the mobile app codebase?
</question>
</vector_search>
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

file_search_agent_instructions = """You are an expert software developer assigned to solve a user provided request.
In order to resolve the user request you will need to retrive relevant code files that you will need to use in later steps.
Your current task is to identify all relevant code files that you will need in order to accomplish the user request.

You will be provided the user task as well as a set of tools available to you in this environment that will allow you to search the codebase for relevant code files.
You may also be given some existing context to work off of.
Use the guidelines below to aid you in this task.

# Guidelines

1. Analyze the user's request to understand the information they are seeking. This may involve breaking the request down into smaller sub requests to identify the specific information needed. You may need to search for these smaller sub requests seperately.
2. Use the search tools available to search the codebase for relevant code files that can help answer all of the user's requests.
3. When you are confident a code file is relevant to the user request, use the `add_file_to_context` tool to add a file to context to indicate that the file is useful and will be needed to fully resolve the user request.
4. A relevant file is defined to be any file needed to answer the user request. This includes code files that contain relevant typing/struct/constant definitions, utility functions, or any other code that is needed to answer the user request.
5. When you believe that you have found all necessary files to answer the user request, use the `done_file_search` tool to indicate that you have added all relevant files to context.

In this environment, you have access to the following tools to assist in fulfilling the user request:

Use one tool at a time. Before every time you use a tool, think step-by-step in a <scratchpad> block about which tools you need to use and in what order to find the information needed to answer the user's question.
You should also update the <dependency_tree> block at every step as a way to keep track of your progress of what you know and what you don't.

Once you have collected and analyzed the relevant snippets, use the `done_file_search` tool to indicate that you are finished searching for files and are confident that your current selection of files is enough to solve the user request completely.

You MUST call tools like this:
<function_call>
<tool_name>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</tool_name>
</function_call>

Here are the tools available:
"""

file_search_agent_user_message = """Here is the user's request:

<user_request>
{question}
</user_request>

Now find all the relevant code files in the codebase to needed to resolve the user request. Use the `semantic_search` and `ripgrep` tools to search for snippets.
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
    model="claude-3-5-sonnet-20240620"
):
    chat_gpt = ChatGPT.from_system_message_string(
        prompt_string=search_agent_instructions + tools_available + "\n\n" + example_tool_calls,
        model=model
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
                # "use_openai": True,
                "model": model
            },
            cloned_repo=cloned_repo,
            llm_state=llm_state,
        )

        user_message = f"<function_call>\n{function_call_response}\n</function_call>"
        
        if function_call_response == "DONE":
            return function_call.function_parameters.get("answer"), function_call.function_parameters.get("sources")
    raise QuestionAnswererException("Could not complete the task. The information may not exist in the codebase.")



file_searcher_tools = [vector_search, ripgrep, view_file, add_files_to_context, done_file_search]

file_searcher_tools_available = """You have access to the following tools to assist in identifying relevant files:

""" + "\n\n".join(tool.get_xml() for tool in file_searcher_tools)

existing_snippet_format = """
<snippet>
<file_name>
{file_name}
</file_name>
<source>
{source}
</source>
</snippet>
"""

def file_searcher(
    question: str,
    cloned_repo: ClonedRepo,
    existing_context: list[Snippet] = [],
    model="claude-3-5-sonnet-20240620"
):
    chat_gpt = ChatGPT.from_system_message_string(
        prompt_string=file_search_agent_instructions + file_searcher_tools_available + "\n\n" + example_tool_calls_file_searcher,
        model=model
    )
    # list of snippets
    relevant_files = []
    user_message = file_search_agent_user_message.format(question=question)
    if existing_context:
        # render existing snippets
        existing_context_string = "<existing_context>"
        for snippet in existing_context:
            snippet_name = f"<{snippet.file_path}:{snippet.start}-{snippet.end}>\n"
            snippet_content = snippet.get_snippet(add_lines=False)
            existing_snippet = existing_snippet_format.format(file_name=snippet_name, source=snippet_content)
            existing_context_string += f"\n{existing_snippet}\n"
        existing_context_string += "</existing_context>"
        user_message += existing_context_string
    
    user_message += file_search_agent_dependency_tree_initialisation
    llm_state = {
        "visited_snippets": set(),
        "visited_questions": set(),
        "request": question,
    }
    for iter_num in range(10):
        function_call_response, function_call = get_function_call(
            chat_gpt,
            user_message,
            file_searcher_tools,
            llm_kwargs={
                # "use_openai": True,
                "model": model
            },
            cloned_repo=cloned_repo,
            llm_state=llm_state,
            relevant_files=relevant_files,
        )

        user_message = f"<function_call>\n{function_call_response}\n</function_call>"
        
        if function_call_response == "DONE":
            return relevant_files
    raise QuestionAnswererException("Could not complete the task. The information may not exist in the codebase.")

if __name__ == "__main__":
#     cloned_repo = MockClonedRepo(
#         _repo_dir = "/tmp/sweep",
#         repo_full_name="sweepai/sweep",
#     )
#     result = file_searcher(
#         question="""In the vector search logic, how would I migrate the KNN to use HNSW instead?
# """,
#         cloned_repo=cloned_repo,
#     )
    # result = rag(
    #     question="What version of django is used in this codebase?",
    #     cloned_repo=cloned_repo,
    # )
    breakpoint() #noqa
