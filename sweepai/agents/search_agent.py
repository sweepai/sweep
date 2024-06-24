from sweepai.agents.agent_utils import Parameter, handle_function_call, tool, validate_and_parse_function_call
from sweepai.agents.question_answerer import QuestionAnswererException, rag, parse_sources, search_codebase
from sweepai.core.chat import ChatGPT, continuous_llm_calls
from sweepai.core.entities import Snippet
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo
from sweepai.utils.str_utils import extract_xml_tag

example_tool_calls = """Here are examples of how to use the tools:

To locate the module that implements a particular feature:
<function_call>
<ask_question_about_codebase>
<question>
Where is the vector database query logic defined?
</question>
</ask_question_about_codebase>
</function_call>

To find all usages of a particular function:
<function_call>
<ask_question_about_codebase>
<question>
List all usages of the add_user_to_team mutation in the codebase.
</question>
</ask_question_about_codebase>
</function_call>

To specify a detail of a particular function:
<function_call>
<ask_question_about_codebase>
<question>
How does the user authentication service handle authentication and logout?
</question>
</ask_question_about_codebase>
</function_call>

Notice that the `question` parameter is a direct natural language search question.

The above are just illustrative examples. Make sure to provide detailed, specific questions to search for relevant snippets in the codebase and only make one function call."""

# Push towards asking more specific questions

search_agent_instructions = """Your job is to find ALL relevant information in the codebase for an intern to write a pull request to the current codebase to resolve the bug report or feature request in the user's GitHub issue. The intern will only use the files presented by you, so make sure to find ALL the files that need changes to resolve the user's issue.

You will be provided with the user's GitHub issue, some initial search results, and the codebase you will be working with. You will be provided with a `ask_question_about_codebase` tool to ask questions about the codebase, and a <scratchpad></scratchpad> to plan your steps and think out loud.

To complete the task, follow these steps:

1. Analyze the user's question and the initial search results to understand the information needed to resolve the issue. Then, think step-by-step to determine everything in step 2 that's relevant to the user's query, as well as which steps may be skipped.

2. Search the codebase for relevant code snippets that can help resolve the issue. Follow this framework to ask questions about the codebase:
    a. Root cause analysis how does the functionality currently work in the codebase and consequently where does the bug or missing feature occur? Be sure to understand the current functionality thoroughly before proceeding.
        Given this information, think step-by-step to identify the root cause. Where should we make changes in the codebase to fix the bug or implement the feature?
            - If there are any uncertainties about the root cause, ask more questions to find more clarifying information about the codebase.
    b. Finding usages: If you need to change how a method is to be used, make sure to find all usages of that method to understand how it is used in the codebase.
    c. Similar features: For feature requests, is there a similar functionality we can reference in the codebase to understand how to implement the desired change?
        i. First, identify a similar functionality that likely already exists in the codebase.
        ii. Then, find the specific file and function that implements this similar functionality and ask where it is located by asking questions about that specific functionality.
    d. Utility functions: What types of files would we need to import, such as utility modules, type definitions and abstractions would be useful? If resolving this issue requires defining a new utility function or module, check if the utility function already exists.
        - Be more broad in your questions to find the utility modules that would be useful for implementing the desired change.
        - Ask multiple questions to find each utility module that would be useful for implementing the desired change.

Start with broader questions to understand the current existing functionality and then narrow down to clarify on specific details. For each of the steps above, identify the steps that are relevant to the user's issue. You may skip steps that are not relevant to the user's issue.

Here is an example of good questions to ask and bad questions to ask:

<example>
Example problem: There is a bug when user's log after authenticating with Google, the user is not redirected to the correct page.

Good questions:

a How do we authenticate and log out users in the user-authentication service?
    - This is a good question to start with because it is broad and provides a good big picture of how the codebase handles the current functionality.
c. How do we currently handle redirecting logged out users for users that signed in using GitHub Auth?
    - This is a good question because it asks about the implementation for a similar feature that does not have the reported issue, which can be used as a reference for the fix. We can use similar utility modules to resolve the errors.
d. Is there a helper function that constructs the redirect URL for logged out users?
    - This is a good question because it asks about a specific utility function that may be used to fix the issue so we don't define a new one.

Bad questions:

- What changes do I need to make to ensure compare that users logged out of Google Auth are redirected to the correct page?
    - This is a bad question the assistant can only retrieve information from the codebase, not provide solutions.
- How do I resolve this issue with the user-authentication service?
    - This is a bad question because it is too vague and does not provide enough context to find the relevant code. Also the assistant cannot provide solutions.
- Where does the error occur in the codebase?
    - This is a bad question because the assistant is not provided with enough context to find the relevant code. The assistant will not be provided with the user's issue, so you must provide full context in your questions that require them.
- What does the spread operator ... do in Typescript?
    - This is a bad question because it is unrelated to the codebase. The assistant can only provide information about the codebase.
</example>

3. Submit a highly-detailed, step-by-step plan for the intern to follow to write the pull request to fix the bug report or feature request to resolve the user's issue.

In this environment, you have access to the following tools to assist in fulfilling the user request:

Use one tool at a time. Before every time you use a tool, think step-by-step in a <scratchpad> block about which tools you need to use and in what order to find the information needed to answer the user's question.

Once you have collected and analyzed the relevant snippets, use the `submit_task` tool to submit the final response to the user's question.

You MUST call them like this:
<function_call>
<$TOOL_NAME>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</$TOOL_NAME>
</function_call>

Here are the tools available:
"""

search_agent_user_message = """Here is the codebase you will be working with:
<repo>
{repo_name}
</repo>

Here is the user's GitHub issue:
<github_issue>
{github_issue}
</github_issue>

Here are some relevant files from initial search results:
{snippets}

Now find all relevant information to answer the question. Use the `ask_question_about_codebase` tool to ask questions about the codebase. Provide the query to search for relevant snippets in the codebase.

Start analyzing the user's request, fully comprehending each line of the input, and then brainstorming questions to ask about the codebase based on the contents of the GitHub issue and your analysis to perform Step A. Root cause analysis."""

NO_TOOL_CALL_PROMPT = """FAILURE
Your last function call was incorrectly formatted. Here is are examples of correct function calls:

For example, to search the codebase for relevant snippets:

<function_call>
<ask_question_about_codebase>
<question>
List all usages of the add_user_to_team mutation in the codebase.
How does the user authentication service handle authentication and logout?
Where is the vector database query logic defined?
</question>
</ask_question_about_codebase>
</function_call>

If you have sufficient sources to answer the question, call the submit_task function with an extremely detailed, well-referenced response in the following format:

<function_call>
<submit_task>
<analysis>
For each snippet, summarize the contents and what it deals with. Indicate all sections of code that are relevant to the user's question. Think step-by-step to reason about how the snippets relate to the question.
</analysis>
<answer>
Provide a detailed response to the user's question.
Reference all relevant entities in the codebase, and provide examples of usages and implementations whenever possible. 
When you mention an entity, be precise and clear by indicating the file they are from. For example, you may say: this functionality is accomplished by calling `foo.bar(x, y)` (from the `Foo` class in `src/modules/foo.py`).
</answer>
<sources>
Code files you referenced in your <answer>. Only include sources that are DIRECTLY REFERENCED in your answer, do not provide anything vaguely related. Keep this section MINIMAL. These must be full paths and not symlinks of aliases to files. Include all referenced utility functions and type definitions. Follow this format:
path/to/file.ext
path/to/other/file.ext
</sources>
</submit_task>
</function_call>

First, in a scratchpad, think step-by-step to identify precisely where you have malformatted the function call. Double-check that you have opening and closing tags for function_call, invoke, tool_name, and parameters. Then, you may make additional search queries using `ask_question_about_codebase` or submit the task using `submit_task`."""

"""
Needed this explanation for Opus, might not need it for GPT-4o
"""
ASK_QUESTION_RESULT_INSTRUCTIONS = """

Recall that the user's original request is:

<issue>
{request}
</issue>{scratchpad}

In your <scratchpad></scratchpad> block, you must follow this format:

Step 1. Summarize the key points from the previous answers.
Step 2. Think step-by-step to determine if the answers you received so far is 100% complete and sufficient.
Step 3a. If the answers received insufficient for any reason, you will need to ask more follow-up questions to complete the current step, use the `ask_question_about_codebase` tool again to ask more questions about the codebase, with more specific questions.
Step 3b. If you have enough information, use the `submit_task` tool to submit the final answer of what to change. Be sure to follow the specified format, including <plan></plan>, <explanation></explanation>, and <sources></sources> XML tags. Each step of the instructions should be actionable and specific, like "change" or "add", instead of "investigate" or "look into". If you must say "investigate" or are unsure about anything, it means you have insufficient information and should ask more questions using the `ask_question_about_codebase` tool."""

SCRATCHPAD_PROMPT = """

And here is your planning in your scratchpad prior to the last `ask_question_about_codebase` call:
<scratchpad>
{scratchpad}
</scratchpad>"""

@tool()
def ask_question_about_codebase(
    question: Parameter("A directed natural language search question to ask about the codebase. This should be in the form of a natural language question, like 'How does the user authentication service handle authentication and logout?'"),
    cloned_repo: ClonedRepo,
    github_issue: str,
    llm_state: dict
):
    results = ""
    relevant_snippets = []
    try:
        answer, sources = rag(question, cloned_repo)
    except QuestionAnswererException as e:
        results += f"<question>\n{question}\n</question>\n<error>\n{e.message}\n</error>\n\n"
    relevant_snippets = parse_sources(sources, cloned_repo)
    results += f"<question>\n{question}\n</question>\n<answer>\n{answer}\n\nSources:\n{sources}\n</answer>\n\n"
    llm_state["questions_and_answers"].append((question, answer, sources))

    relevant_files_string = ""
    for snippet in relevant_snippets:
        relevant_files_string += f"<snippet>\n<file_path>\n{snippet.denotation}\n</file_path>\n<source>\n{snippet.get_snippet(add_lines=False)}\n</source>\n</snippet>\n"
    if relevant_files_string:
        relevant_files_string = f"Here is a list of files cited in the answers to the questions:\n{relevant_files_string}\n\n"
    scratchpad = llm_state["scratchpad"]
    results = relevant_files_string + results.strip() + ASK_QUESTION_RESULT_INSTRUCTIONS.format(
        request=github_issue,
        scratchpad=SCRATCHPAD_PROMPT.format(scratchpad=scratchpad) if scratchpad.strip() else ""
    )
    return results

@tool()
def submit_task(
    plan: Parameter("Extremely detailed step-by-step plan of the code changes you will make in the repo to fix the bug or implement the feature to resolve the user's issue."),
    explanation: Parameter("List each snippet mentioned in the plan and the role it plays in the plan."),
    sources: Parameter("Code files you referenced in your <answer>. Only include sources that are DIRECTLY REFERENCED in your answer, do not provide anything vaguely related."),
    cloned_repo: ClonedRepo
):
    error_message = ""
    try:
        parse_sources(sources, cloned_repo)
    except Exception as e:
        error_message = str(e)
    if error_message:
        return error_message
    else:
        return "DONE"

tools = [
    ask_question_about_codebase,
    submit_task
]

tools_available = """You have access to the following tools to assist in fulfilling the user request:
""" + "\n".join([tool.get_xml() for tool in tools])

def search(
    github_issue: str,
    cloned_repo: ClonedRepo,
    snippets: list[Snippet]=[],
):
    chat_gpt = ChatGPT.from_system_message_string(
        prompt_string=search_agent_instructions + tools_available + "\n\n" + example_tool_calls,
    )

    user_message = search_agent_user_message.format(
        repo_name=cloned_repo.repo_full_name,
        github_issue=github_issue,
        snippets="\n".join([snippet.xml for snippet in snippets])
    )
    llm_state = {
        "scratchpad": "",
        "questions_and_answers": []
    }

    for _ in range(10):
        response = continuous_llm_calls(
            chat_gpt,
            content=user_message,
            stop_sequences=["\n</function_call>"],
            use_openai=True
        )

        function_call = validate_and_parse_function_call(
            response,
            chat_gpt,
            tools=tools
        )

        scratchpad = extract_xml_tag(response, "scratchpad") or ""
        llm_state["scratchpad"] += "\n" + scratchpad

        if function_call is None:
            function_call_response = ""
            user_message = NO_TOOL_CALL_PROMPT
        else:
            function_call_response = handle_function_call(function_call, tools, cloned_repo=cloned_repo, github_issue=github_issue, llm_state=llm_state)
            user_message = f"<function_output>\n{function_call_response}\n</function_output>"
        
        if "DONE" == function_call_response:
            for question, answer, sources in llm_state["questions_and_answers"]:
                print(f"Question: {question}")
                print(f"Answer:\n{answer}")
                print(f"Sources:\n{sources}")
                print('\n\n')
            return {
                "questions_and_answers": llm_state["questions_and_answers"],
                "explanation": function_call.function_parameters.get("explanation"),
                "sources": parse_sources(function_call.function_parameters.get("sources"), cloned_repo)
            }
    raise Exception("Failed to complete the task.")

if __name__ == "__main__":
    import os

    REPO_NAME = os.environ["REPO_NAME"]
    QUERY = os.environ["QUERY"]

    org_name, repo_name = REPO_NAME.split("/")
    cloned_repo = MockClonedRepo(
        _repo_dir=f"/mnt/sweep_benchmark/repos/{repo_name}",
        repo_full_name=REPO_NAME,
    )
    snippets = search_codebase(
        QUERY,
        cloned_repo,
    )
    try:
        results = search(
            # "Fix the parallelization bug in our vector DB.",
            # "In vector_db.py, migrate our KNN algorithm to use HNSW instead",
            QUERY,
            cloned_repo,
            snippets=snippets
        )
        breakpoint() # noqa
    except Exception as e:
        import pdb # noqa
        pdb.post_mortem()
        raise e
