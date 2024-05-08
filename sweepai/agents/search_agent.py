import re
from sweepai.agents.modify import validate_and_parse_function_call
from sweepai.agents.question_answerer import CORRECTED_SUBMIT_SOURCES_FORMAT, QuestionAnswererException, rag
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Snippet
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
<tool_name>ask_questions_about_codebase</tool_name>
<description>
</description>
<parameters>
<parameter>
<name>questions</name>
<type>str</type>
<description>
A list of detailed, specific natural language search question to ask about the codebase. This should be in the form of a natural language question, like "How do we the user-provided password hash against the stored hash from the database in the user-authentication service?". Each question will be provided to the assistant with no additional context, so be sure to refer to provide full context of the issue for each question. The question should be based on the current codebase. One question per line.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>submit_task</tool_name>
<description>
Once you have found all the information you need to resolve the issue, use this tool to submit the final response to start writing code changes.
</description>
<parameters>
<parameter>
<name>plan</name>
<type>str</type>
<description>
Extremely highly detailed step-by-step plan of the code changes you will make in the repo to fix the bug or implement the feature to resolve the user's issue. 
If you have any doubts of the correctness of your answer, you should ask more questions using the `ask_questions_about_codebase` tool.
You will use actionable terms like "change" and "add" to describe the changes you will make, referencing specific methods or modules, instead of terms like "investagate" or "look into", as these should just be done by asking more questions.
</description>
</parameter>
<parameter>
<name>explanation</name>
<type>str</type>
<description>
List each snippet mentioned in the plan and the role it plays in the plan. Do NOT actually advise the user to make the changes, just explain how each particular snippet could be used.
</description>
</parameter>
<parameter>
<name>sources</name>
<type>str</type>
<description>
Code files you referenced in your <answer>. Only include sources that are DIRECTLY REFERENCED in your answer, do not provide anything vaguely related. Keep this section MINIMAL. These must be full paths and not symlinks of aliases to files. Include all referenced utility functions and type definitions. Follow this format:
path/to/file.ext - justification and which section of the file is needed
path/to/other/file.ext - justification and which section of the file is needed
</description>
</parameter>
</parameters>
</tool_description>"""

example_tool_calls = """Here are examples of how to use the tools:

To ask questions about the codebase:
<function_call>
<invoke>
<tool_name>ask_questions_about_codebase</tool_name>
<parameters>
<questions>
How do we the user-provided password hash against the stored hash from the database in the user-authentication service?
How are GraphQL mutations constructed for updating a user's profile information, and what specific fields are being updated?
How do the current React components render the product carousel on the homepage, and what library is being used for the carousel functionality?
How do we currently implement the endpoint handler for processing incoming webhook events from Stripe in the backend API, and how are the events being validated and parsed?
</questions>
</parameters>
</invoke>
</function_call>

Notice that the `query` parameter is an extremely detailed, specific natural language search question.

The above are just illustrative examples. Make sure to provide detailed, specific questions to search for relevant snippets in the codebase and only make one function call."""

# Push towards asking more specific questions

search_agent_instructions = """Your job is to find all relevant information in the codebase to write a high quality, detailed, step-by-step plan for an intern to write a pull request to the current codebase to resolve the bug report or feature request in the user's GitHub issue.

You will be provided with the user's GitHub issue and the codebase you will be working with. You will be provided with a `ask_questions_about_codebase` tool to ask questions about the codebase.

To complete the task, follow these steps:

1. Analyze the user's question to understand the information needed to resolve the issue.

2. Search the codebase for relevant code snippets that can help resolve the issue. Follow this sequence to ask questions about the codebase:
    Step A. Root cause analysis - where is the bug or missing feature occurring in the codebase?
        a. How does the functionality currently work in the codebase and consequently where does the bug or missing feature occur? Be sure to understand the current functionality EXTREMELY thoroughly before proceeding.
            i. Start by asking about the general functionality of the codebase to understand how the current feature works.
            ii. Then, ask several highly specified questions about specific components of the functionality to pinpoint where the bug or missing feature may occur.
        Given this information, think step-by-step to identify the root cause. Where should we make changes in the codebase to fix the bug or implement the feature?
            - If there are any uncertainties about the root cause, ask more questions to find more clarifying information about the codebase.

    Step B. Implementation - what are useful modules in the codebase that can be helpful for implementing the desired change?
        b. Is there a similar functionality we can reference in the codebase to understand how to implement the desired change?
            i. First, identify a similar functionality that likely already exists in the codebase. For example, if there's a flag in the handler for Jira already, we can read that handler for reference for implementing the same flag for Linear.
            ii. Then, find the specific file and function that implements this similar functionality and ask where it is located by asking questions about that specific functionality.
        c. What types of files would we need to import, such as utility modules, type definitions and abstractions would be useful? If resolving this issue requires defining a new utility function or module, check if the utility function already exists.
            - Be more broad in your questions to find the utility modules that would be useful for implementing the desired change.
            - Ask multiple questions to find each utility module that would be useful for implementing the desired change.
    
    Step C. Testing - how can we test the changes made to the codebase?
        d. Determine if and where there are the unit tests located that would need to be updated to reflect the changes made to the codebase.

Each of the three steps should use it's own function call to the `ask_questions_about_codebase` tool, so you should make at least three separate function calls to the `ask_questions_about_codebase` tool.

At the start of each step, you should think step-by-step in the <scratchpad> to better understand the issue at hand and brainstorm good questions for the that step. When you plan for the Root cause analysis step, ONLY decide on questions that would be valuable for that step, because you will have more informative questions later on. Then, if you have any doubts or uncertainties about the correctness of your answer, you should follow-up questions using the `ask_questions_about_codebase` tool before moving onto the next step.

Here is an example of good questions to ask and bad questions to ask:

<example>
Example problem: There is a bug when user's log after authenticating with Google, the user is not redirected to the correct page.

Good questions:

First `ask_questions_about_codebase` call:
Step A. Root cause analysis
    a.i How do we authenticate and log out users in the user-authentication service?
        - This is a good question to start with because it is broad and provides a good big picture of how the codebase handles the current functionality.
    a.ii How do we currently compare the authentication token against the stored hash from the database in the user-authentication service for users signing in using Google Auth?
        - This is a good follow-up question to the previous question because it narrows down the focus to a specific part of the codebase.

Second `ask_questions_about_codebase` call:
Step B. Implementation
    b. How do we currently handle redirecting logged out users for users that signed in using GitHub Auth?
        - This is a good question because it asks about the implementation for a similar feature that does not have the reported issue, which can be used as a reference for the fix. We can use similar utility modules to resolve the errors.
    c. Is there a helper function that constructs the redirect URL for logged out users?
        - This is a good question because it asks about a specific utility function that may be used to fix the issue so we don't define a new one.

Third `ask_questions_about_codebase` call:
Step C. Testing
    d. Where are the unit tests located that test the `logout` function in `src/services/user-authentication`?
        - This is a good question because it asks about the location of the unit tests that need to be updated to reflect the changes made to the codebase.

Remember that when you do planning in the <scratchpad>, you should only plan for the current step.

Bad question:

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

search_agent_user_message = """Here is the codebase you will be working with:
<repo>
{repo_name}
</repo>

Here is the user's GitHub issue:
<github_issue>
{github_issue}
</github_issue>

Now find all relevant information to answer the question. Use the `ask_questions_about_codebase` tool to ask questions about the codebase. Provide the query to search for relevant snippets in the codebase.

Start analyzing the user's request, fully comprehending each line of the input, and then brainstorming questions to ask about the codebase based on the contents of the GitHub issue and your analysis to perform Step A. Root cause analysis."""

NO_TOOL_CALL_PROMPT = """FAILURE
Your last function call was incorrectly formatted. Here is are examples of correct function calls:

For example, to search the codebase for relevant snippets:

<function_call>
<invoke>
<tool_name>ask_questions_about_codebase</tool_name>
<parameters>
<questions>
Where is the function that compares the user-provided password hash against the stored hash from the database in the user-authentication service?
Where is the code that constructs the GraphQL mutation for updating a user's profile information, and what specific fields are being updated?
Where are the React components that render the product carousel on the homepage, and what library is being used for the carousel functionality?
Where is the endpoint handler for processing incoming webhook events from Stripe in the backend API, and how are the events being validated and parsed?
</questions>
</parameters>
</invoke>
</function_call>

If you have sufficient sources to answer the question, call the submit_task function with an extremely detailed, well-referenced response in the following format:

<function_call>
<invoke>
<tool_name>submit_task</tool_name>
<parameters>
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
</parameters>
</invoke>
</function_call>

First, in a scratchpad, think step-by-step to identify precisely where you have malformatted the function call. Double-check that you have opening and closing tags for function_call, invoke, tool_name, and parameters. Then, you may make additional search queries using `ask_questions_about_codebase` or submit the task using `submit_task`."""

ASK_QUESTIONS_RESULT_INSTRUCTIONS = """

Recall that the user's original request is:

<issue>
{request}
</issue>{scratchpad}

Remember that the three steps are:
Step A. Root cause analysis - where is the bug or missing feature occurring in the codebase?
    - How does the functionality currently work in the codebase and consequently where does the bug or missing feature occur?
Step B. Implementation - what are useful modules in the codebase that can be helpful for implementing the desired change?
    - Is there a similar functionality we can reference in the codebase to understand how to implement the desired change?
    - What types of utility modules, type definitions, and abstractions would be useful? Brainstorm useful utility modules we will need to use and ask a question about each one of them.
Step C. Testing - how can we test the changes made to the codebase?
    - Determine if and where there are the unit tests located that would need to be updated to reflect the changes made to the codebase.

Remember to be specific with your questions with full context, since the assistant is only provided your questions and not the context of the issue.

First, summarize the key points from the previous answers.

Then, think step-by-step in a single <scratchpad> block to determine if the answers you received so far is 100% complete and sufficient to move onto the next step.

If the answers received are not 100% complete and suffiient, you will need to ask more follow-up questions to complete the current step, use the `ask_questions_about_codebase` tool again to ask more detailed, specific questions about the codebase.

Otherwise, if you have enough information to move onto the next step, first determine the step you were just on and what the next step is. Then, proceed to list out information you will need to complete the next step. Lastly, brainstorm questions to ask about the codebase to find the information needed to answer the user's question.

If have just completed the last step, use the `submit_task` tool to submit the final detailed step-by-step plan of what to change. Each step of the instructions should be actionable and specific, like "change" or "add", instead of "investigate" or "look into". If you must say "investigate", it means you have insufficient information and should ask more questions using the `ask_questions_about_codebase` tool."""

SCRATCHPAD_PROMPT = """

And here is your planning in your scratchpad prior to the last `ask_questions_about_codebase` call:
<scratchpad>
{scratchpad}
</scratchpad>"""

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

def extract_xml_tag(string: str, tag: str, include_closing_tag: bool = True):
    pattern = f"<{tag}>(.*?)</{tag}>" if include_closing_tag else f"<{tag}>(.*?)(\Z|</{tag}>)"
    match_ = re.search(pattern, string, re.DOTALL)
    if match_ is None:
        return None
    return match_.group(1).strip("\n")

def search(
    github_issue: str,
    cloned_repo: ClonedRepo,
):

    # snippets_text = "\n\n".join([SNIPPET_FORMAT.format(
    #     denotation=snippet.denotation,
    #     contents=snippet.content,
    # ) for snippet in rcm.current_top_snippets[::-1]])

    chat_gpt = ChatGPT.from_system_message_string(
        prompt_string=search_agent_instructions + tools_available + "\n\n" + example_tool_calls,
    )

    user_message = search_agent_user_message.format(
        repo_name=cloned_repo.repo_full_name,
        github_issue=github_issue
    )
    llm_state = {
        "scratchpad": "",
        "questions_and_answers": []
    }

    for _ in range(10):
        response = chat_gpt.chat_anthropic(
            user_message,
            model="claude-3-opus-20240229",
            stop_sequences=["</function_call>"],
        ) + "</function_call>"

        function_call = validate_and_parse_function_call(
            response,
            chat_gpt
        )

        scratchpad = extract_xml_tag(response, "scratchpad") or ""
        llm_state["scratchpad"] += "\n" + scratchpad

        if function_call is None:
            user_message = NO_TOOL_CALL_PROMPT
        else:
            function_call_response = handle_function_call(function_call, cloned_repo, github_issue, llm_state)
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
                "sources": function_call.function_parameters.get("sources")
            }
    raise Exception("Failed to complete the task.")

def handle_function_call(function_call: AnthropicFunctionCall, cloned_repo: ClonedRepo, github_issue, llm_state: dict):
    if function_call.function_name == "ask_questions_about_codebase":
        if "questions" not in function_call.function_parameters:
            return "Please provide a question to search the codebase."
        questions = function_call.function_parameters["questions"].strip()
        results = ""
        relevant_snippets = []
        for question in questions.splitlines():
            if not question.strip():
                continue
            try:
                answer, sources = rag(question, cloned_repo)
            except QuestionAnswererException as e:
                results += f"<question>\n{question}\n</question>\n<error>\n{e.message}\n</error>\n\n"
                continue
            for line in sources.splitlines():
                snippet_denotation  = line.split(" - ")[0]
                file_path, line_numbers = snippet_denotation.split(":")
                start_line, end_line = line_numbers.split("-")
                if file_path not in relevant_snippets:
                    relevant_snippets.append(Snippet(
                        content=cloned_repo.get_file_contents(file_path),
                        start=start_line,
                        end=end_line,
                        file_path=file_path,
                    ))
            results += f"<question>\n{question}\n</question>\n<answer>\n{answer}\n\nSources:\n{sources}\n</answer>\n\n"
            llm_state["questions_and_answers"].append((question, answer, sources))
        relevant_files_string = ""
        for snippet in relevant_snippets:
            relevant_files_string += f"<snippet>\n<file_path>\n{snippet.denotation}\n</file_path>\n<source>\n{snippet.get_snippet(add_lines=False)}\n</source>\n</snippet>\n"
        if relevant_files_string:
            relevant_files_string = f"Here is a list of files cited in the answers to the questions:\n{relevant_files_string}\n\n"
        scratchpad = llm_state["scratchpad"]
        results = relevant_files_string + results.strip() + ASK_QUESTIONS_RESULT_INSTRUCTIONS.format(
            request=github_issue,
            scratchpad=SCRATCHPAD_PROMPT.format(scratchpad=scratchpad)
        )
        print(results)
        # breakpoint()
        return results
    elif function_call.function_name == "submit_task":
        for key in ("plan", "explanation", "sources"):
            if key not in function_call.function_parameters:
                return f"Please provide a {key} to submit the task."
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
    try:
        search(
            "Fix the parallelization bug in our vector DB.",
            cloned_repo,
        )
    except Exception as e:
        import pdb
        pdb.post_mortem()
        raise e
