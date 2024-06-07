"""
List of common prompts used across the codebase.
"""

# Following two should be fused
system_message_prompt = """\
You are a brilliant and meticulous engineer assigned to write code for the following Github issue. When you write code, the code works on the first try, is syntactically perfect and is fully implemented. You have the utmost care for the code that you write, so you do not make mistakes and every function and class will be fully implemented. When writing tests, you will ensure the tests are fully implemented, very extensive and cover all cases, and you will make up test data as needed. Take into account the current repository's language, frameworks, and dependencies."""

repo_description_prefix_prompt = "\nThis is a description of the repository:"

rules_prefix_prompt = (
    "\nThese are the user's preferences and instructions. Use them as needed"
)

human_message_prompt = [
    {
        "role": "user",
        "content": """{relevant_snippets}""",
        "key": "relevant_snippets",
    },
    {
        "role": "user",
        "content": """{relevant_directories}""",
        "key": "relevant_directories",
    },
    {
        "role": "user",
        "content": """{relevant_commit_history}""",
        "key": "relevant_commit_history",
    },
    {
        "role": "user",
        "content": """<repo_tree>
{tree}
</repo_tree>""",
        "key": "relevant_tree",
    },
    {
        "role": "user",
        "content": """# Repo & Issue Metadata
Repo: {repo_name}: {repo_description}
Issue Title: {title}{description}""",
        "key": "metadata",
    },
]

human_message_review_prompt = [
    {
        "role": "user",
        "content": """{relevant_snippets}""",
    },
    {
        "role": "user",
        "content": """{relevant_directories}""",
    },
    {"role": "user", "content": """{plan}"""},
    {
        "role": "user",
        "content": """{diffs}""",
    },
]

snippet_replacement_system_message = f"""{system_message_prompt}

You are selecting relevant snippets for this issue. You must only select files that would help you understand the context of this issue.

## Snippet Step

In order to address this issue, what required information do you need about the snippets? Only include relevant code and required file imports that provides you enough detail about the snippets for the problems:

Note: Do not select the entire file. Only select relevant lines from these files. Keep the relevant_snippets as small as possible.

<contextual_thoughts>
* Thought_1
* Thought_2
...
</contextual_thoughts>

<relevant_snippets>
folder_1/file_1.py:1-13
folder_2/file_2.py:42-75
...
</relevant_snippets>
"""

snippet_replacement = """Based on this issue, determine what context is relevant for the file changes. In the relevant_snippets, do not write the entire file lines. Choose only the most important lines.

Complete the Snippet Step."""

diff_section_prompt = """
<file_diff file="{diff_file_path}">
{diffs}
</file_diff>"""

review_prompt = """\
Repo & Issue Metadata:
<metadata>
Repo: {repo_name}: {repo_description}
Issue Title: {title}
Issue Description:
{description}
</metadata>

The code was written by an inexperienced programmer. Carefully review the code diffs in this pull request. Use the diffs along with the original plan to verify that each step of the plan was implemented correctly.

Check for the following:
* Missing imports
* Incorrect functionality
* Other errors not listed above
* Incorrect/broken tests

Indicate all breaking changes. Do not point out stylistic issues. Ensure that the code resolves the issue requested by the user and every function and class is fully implemented.

Respond in the following format:c
<diff_analysis>
Check each file_diff function by function and confirm whether it was both implemented and implemented correctly.
...
</diff_analysis>"""

final_review_prompt = """\
Given the diff_analysis write a direct and concise GitHub review comment. Be extra careful with unimplemented sections and do not nitpick on formatting.
If there is additional work to be done before this PR is ready, mention it. If there are no changes required, simply say "No changes required."
In case changes are required, keep in mind the author is an inexperienced programmer and may need a pointer to the files and specific changes.
Follow this format:
<changes_required>
Write Yes if the changes are required or No if they are not required.
</changes_required>
<review_comment>
Mention any changes that need to be made, using GitHub markdown to format the comment.
- Change required in file on line x1-x2
- Change required in file on line y1-y2
...
</review_comment>"""

issue_comment_prompt = """
<comment username="{username}">
{reply}
</comment>"""

# Prompt for comments
human_message_prompt_comment = [
    {
        "role": "user",
        "content": """{relevant_snippets}""",
    },
    {
        "role": "user",
        "content": """{relevant_directories}""",
    },
    {
        "role": "user",
        "content": """<repo_tree>
{tree}
</repo_tree>""",
    },
    {
        "role": "user",
        "content": """# Repo & Pull Request Metadata
This is the repository as well as the original intent of the Pull Request.
Repo: {repo_name}: {repo_description}
Pull Request Title: {title}
Pull Request Description: {description}{relevant_docs}""",
    },
    {
        "role": "user",
        "content": """These are the previous file changes
{diff}""",
    },
    {
        "role": "user",
        "content": """Please handle the user review comment using the snippets, pull request title, pull request description, and the file changes.
User pull request review: \"{comment}\"""",
    },
]

cot_retrieval_prompt = """
Gather information to solve the problem. Use "finish" when you feel like you have sufficient information.
"""

files_to_change_abstract_prompt = """Write an abstract minimum plan to address this issue in the least amount of change possible. Try to originate the root causes of this issue. Be clear and concise. 1 paragraph."""

files_to_change_system_prompt = """You are an AI assistant helping an intern write code to resolve a GitHub issue. The user will provide code files, a description of the issue, and relevant parts of the codebase.
Your role is to analyze the issue and codebase, then provide a clear, step-by-step plan the intern can follow to make the necessary code changes to resolve the issue. Reference specific files, functions, variables and code files in your plan. Organize the steps logically and break them into small, manageable tasks.
Prioritize using existing code and functions to make efficient and maintainable changes. Ensure your suggestions fully resolve the issue.

Take these steps:
1. Analyze the issue and codebase to understand the problem.

2. Create a detailed plan for the intern to follow, including all necessary changes to resolve the issue.
    - When modifying code you MUST do the following:
        - Modify step 1. Copy the original code in <original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are not permitted.
        - Modify step 2. Write the new code in <new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>.

3. List all of the relevant files to reference while making changes, one per line."""

fix_files_to_change_system_prompt = """You proposed a plan previously but there are some errors in your plan. You must resolve these errors before proceeding.

For each error, follow these steps:
1. Identify the error and what went wrong.
2. Select a strategy to fix the error. You have four options:
    a. Fix invalid contents in the plan.
    b. Correct a file path. This is preferred if the code does not need to be changed.
    c. Drop the task.
"""

fix_files_to_change_prompt = """You proposed a plan. However, your proposed plan has the following errors:

<errors>
{error_message}
</errors>

You must resolve these errors before proceeding. Respond in the following format:

<error_resolutions>
<error_resolution>
Error #0: Summary of the error

You will first think step-by-step about the error, and then either rewrite the instructions with the corrected fix, or drop the task.

<thinking>
Analyze extremely carefully in great detail what went wrong, including the file path and the specific code block that needs to be modified. 
If you have failed to copy code verbatim, describe precisely what is different between the code you provided and the code in the actual file. Reference the exact lines in the diff provided showing the difference between your original code and what is in the file.
</thinking>

Then, let's resolve the errors in your proposed plan. You MUST pick ONE of the following options:
a. If you would like to patch the corresponding task of the plan, create a modify block with an index. The index should be equivalent to the error number of this error_resolution block, so it must be one of the following allowed integers: {allowed_indices}.
b. If the error is a file path, correct the file path. This is preferred if the code does not need to be changed.
c. Otherwise, if you absolutely cannot resolve the error, drop the task. 

You must pick exactly ONE option from the three options presented above. Follow this format:

Option a: To patch an invalid modify:

<modify file="file_path" index="0">
Rewritten instructions to resolve the error. Update the original_code and new_code blocks as required, ensuring that the <original_code> block contains the actual code from the file.

Update <original_code> with the necessary changes:
<original_code>
The corrected code from the file verbatim. Abbreviating, missing indents, paraphrasing and placeholder code are NOT permitted. It is absolutely critical that the indentation is correct and matches the source code EXACTLY.
</original_code>

Update <new_code> block with the necessary changes:
<new_code>
Updated new code, based on the corrections in <original_code>. Ensure all newly introduced indents and comments are propagated here.
</new_code>
</modify>

Option b: To fix an invalid file path, such as a non-existent directory (this is preferred if the code does not need to be changed):

Enter "COPIED_FROM_PREVIOUS_MODIFY" verbatim into the modify block to copy the code from the previous change.
Example:
<modify file="file_path" index="0">
COPIED_FROM_PREVIOUS_MODIFY
</modify>

Option c: Otherwise, if you absolutely cannot resolve the error, drop the task like so:

<drop>Index of the task to drop</drop>
</error_resolution>

[additional <error_resolution> blocks as needed, for the same file or different files]
</error_resolutions>"""

test_files_to_change_system_prompt = """You are an AI assistant helping an intern write tests to validate his code that aims to resolve a GitHub issue. The user will provide code files, a description of the issue, and relevant parts of the codebase.
Your role is to analyze the issue and codebase, then provide a clear, step-by-step plan the intern can follow to make the necessary code changes to resolve the issue. Reference specific files, functions, variables and code files in your plan. Organize the steps logically and break them into small, manageable tasks.
Prioritize using existing code and functions to make efficient and maintainable changes. Ensure your suggestions fully resolve the issue.

Take these steps:
1. Analyze the issue and codebase to understand the problem.

2. Create a detailed plan for the intern to follow, including all necessary changes to resolve the issue.
    - When modifying code you MUST do the following:
        - Modify step 1. Copy the original code in <original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are not permitted.
        - Modify step 2. Write the new code in <new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>.

3. List all of the relevant files to reference while making changes, one per line."""

test_files_to_change_prompt = """Now let's add tests to the code changes you made in the previous step. You will need to add or update tests to ensure that the changes you made are correct and do not break existing functionality.

Please use the following XML format for your response:

# 1. Issue Analysis:
<issue_analysis>
a. Identify the functional changes made and locate the tests for the edited code. Respond in the following format:

  - File path 1:
    a. Identify the edited functions and classes.
    b. Then, locate the tests for this module by checking for the most relevant test that imports the file in the <imports> section.
    c. List and summarize all tests in each relevant test from step b. Then, identify the most similar tests we can copy with some minor edits. For example, if you need to test a functionality with a specific new feature, you can copy the test of the base functionality. Be as specific as possible. Follow the following format:

First test name, which section it is located in, and which file it is from.
```
Copy of test code here
```

Second test name, which section it is located in, and which file it is from.
```
Copy of test code here
```

    d. Detail all of the tests that need to be added or updated to validate the changes. Reference the provided code files, summaries, entity names, and necessary files/directories. Be complete and precise. Follow the following format:
      - First place to make a change or create a new test in extreme detail.
      - Second place to make a change or create a new test in extreme detail.

  - File path 2:
    a. Identify the edited functions and classes.
    b. Then, locate the tests for this module by checking for the most relevant test that imports the file in the <imports> section.
    c. List and summarize all tests in each relevant test from step b. Then, identify the most similar tests we can copy with some minor edits. For example, if you need to test a functionality with a specific new feature, you can copy the test of the base functionality. Be as specific as possible. Follow the following format:

First test name, which section it is located in, and which file it is from.
```
Copy of test code here
```

Second test name, which section it is located in, and which file it is from.
```
Copy of test code here
```

    d. Detail all of the tests that need to be added or updated to validate the changes. Reference the provided code files, summaries, entity names, and necessary files/directories. Be complete and precise. Follow the following format:
      - First place to make a change or create a new test in extreme detail.
      - Second place to make a change or create a new test in extreme detail.
[additional files as needed]

b. List ALL relevant read-only utility modules from the provided set and specify where they can be used. These are not files you need to make changes to but files you need to read while making changes in other tests, including:
  - Relevant source code that we're testing
  - Type definitions, interfaces, and schemas
  - Helper functions
  - Frontend components
  - Database services
  - API endpoints
[additional relevant modules as needed]
</issue_analysis>

# 2. Plan:
<plan>  
<create file="file_path_1">
Instructions for creating the new file. Reference imports and entity names. Include relevant type definitions, interfaces, and schemas.
</create>
[additional creates]

<modify file="file_path_2"> 
One sentence explanation of the change. Instructions for modifying one section of the file.

1. Reference the original code in <original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are not permitted. This block must NOT be empty.

2. Write the new code in <new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>.
</modify>

<modify file="file_path_2">
One sentence explanation of the change. Instructions for modifying one section of the file.

1. Reference the original code in <original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are not permitted. This block must NOT be empty.

2. Write the new code in <new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>.

Use multiple <modify> blocks for the same file to separate distinct changes.
</modify>

[additional modifies as needed, for the same file or different files]
</plan>

# 3. Relevant Modules:
<relevant_modules>
[List of all relevant files to reference while making changes, one per line] 
</relevant_modules>""" # + files_to_change_example TODO: test separately

gha_files_to_change_system_prompt = """You are an AI assistant for analyzing failing errors in a developer's code. You will be provided code files, a description of the issue, the error log, relevant parts of the codebase, and the changes he's made.

Your role is to analyze the issue and codebase. Reference specific files, functions, variables and code files in your analysis.

Take these steps:
1. Analyze the issue, codebase and existing changes to understand the problem.

2. List ALL new errors that have appeared in the GitHub Action logs and their corresponding root causes. Identify ALL the entities that need to be updated to resolve these errors. You are diligent and won't miss any errors or entities."""

gha_files_to_change_system_prompt_2 = """You are an AI assistant for writing code to fix failing errors in a developer's code. You will be provided code files, a description of the issue, the error log, relevant parts of the codebase, and the changes he's made. You may only modify edit files to resolve the issue.

Your role is to analyze the issue and codebase, then write out code changes to fix the errors using the proposed diff format. Reference specific files, functions, variables and code files in your plan.
Prioritize using existing code and functions to make efficient and maintainable changes. Ensure your suggestions fully resolve the issue.

Take these steps:
Create a set of code to remove and code to add, including all necessary changes to resolve the issue, in the following format:
Step 1. Reference the original code in <original_code> tags, copying them VERBATIM from the file, with correct indentation and whitespace.
    - Do NOT paraphrase or abbreviate the source code.
    - Placeholder comments like "# existing code" are not permitted.
    - Start with the closest header several lines before the target code and end with the closest end of the block or several lines after the code.
Step 2. Write the new code in <new_code> tags, specifying necessary imports and including relevant type definitions, interfaces, and schemas.
    - BE EXACT as this code will replace the mentioned <original_code>.
Step 3. Look carefully to find all similar changes (potentially unreported) in the code that need to be made in other parts of the same file. Address those as well."""

gha_files_to_change_prompt = """Your job is to analyze the provided issue, error log, relevant parts of the codebase, and changes he's made to understand the requested change.

Follow the following XML format:

# 1. Thinking:
<thinking>
a. Summarize what the original GitHub issue is and asks us to do.

b. List ALL the changes made so far in extreme detail. Be absolutely complete. Follow this format:
    - File path 1:
        - Description of first diff hunk in extreme detail.
        - Description of second diff hunk in extreme detail.
        [additional changes as needed]
    - File path 2:
        - Description of first diff hunk in extreme detail.
        - Description of second diff hunk in extreme detail.
        [additional changes as needed]
    [additional files as needed]
</thinking>

# 2. Reflect:
<reflection>
a. List out all the previous error logs that were solved.
b. List out all previous error logs that are still present or only partially solved.
c. Identify the number of errors, and list out the indices of all the new Github Action error logs that you must now solve and potential root causes and solutions.
- Error 1/n: For each error answer the following questions:
    1. What is the error message? Repeat it verbatim. Is this a repeat error? If so, you may skip the rest of the questions and simply reference the first appearance of this error.
    2. What is the root cause of the error? Explain why.
    3. How can we resolve the error? Be complete and precise.
    4. If we make the fix, what are the potential side effects? Will the fix break other parts of the code? For example, if we change a function signature, will we need to update all the calls to that function?
    5. If you identify potential side effects create - Side Effect #n block and describe the changes that need to be made in order to fix the side effect.
[repeat for all errors]
</reflection>"""

gha_files_to_change_prompt_2 = """Now that you've analyzed the issue and error logs, your job is to write code changes to help resolve the errors in his code while also resolving the GitHub issue.
For each unique error log identified in the previous step, you will need to provide a set of code changes to fix the error.

Guidelines:
<guidelines>
- Always include the full file path and reference the provided files 
- Prioritize using existing code and utility methods to minimize writing new code
- Break the task into small steps, with each <modify> section for each logical code block worth of change. Use multiple <modify> blocks for the same file if there are multiple distinct changes to make in that file, such as for imports.
- A <modify> block must contain exactly one change in one <new_code> tag.
- To remove code, replace it with empty <new_code> tags.
- Do not make a change that has already been made by the developer.
<guidelines>

Please use the following XML format for your response:

<plan>
There are a total of n errors. List ALL the types of error messages in the current error logs and their root causes. Follow this format:

<error_analysis index="1">
Error message 1/n: Identify the error message.
1. Then, find all lines of code that may have the same failure as the erroring lines of code.
2. Identify the root cause of the error, i.e. whether the error is due to a missing change in the tests or the source code. Most of the time, the test case has yet to be updated.
3. Explain how to resolve the error in the test case. Be complete and precise. Remember that to resolve the error in a way such that the test case is still valid. Do not simply apply a band-aid solution to make the error go away.
4. Look carefully to find all similar changes (potentially unreported) in the code that need to be made in other parts of the same file. Address those as well.

Then, based on the analysis, propose a fix by following the format below. If the error has already been fixed, you can skip this step.

<modify file="file_path"> 
Instructions for modifying one section of the file. Each block must have exactly one original_code and one new_code block.

a. Describe the section of code that needs to be modified.
<original_code>
Copy the original_code here VERBATIM from the file.
Do NOT paraphrase or abbreviate the source code.
Placeholder comments like "# existing code" are not permitted.
Start a few lines before the target code to change and end a few lines after.
Do not edit the same area of code more than once to avoid merge conflicts with other modifies.
</original_code>

b. Describe the changes that need to be made to the code.
<new_code>
Write the new code in <new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>. This code MUST be different from the original_code.
</new_code>

Use multiple <modify> blocks for the same file to separate distinct changes, such as for imports.
</modify>

Then, determine if there are similar issues that we should also resolve. Make as many additional modify blocks as needed until ALL similar issues are resolved.
Any issue that doesn't have a corresponding modify block will not be fixed, you must make modify blocks for every single issue identified.
Do not attempt to fix multiple issues with a single modify block, each issue must have its own modify block.
</error_analysis>
[additional <error_analysis> blocks as needed, for ALL error messages in the error logs
</plan>"""

plan_selection_prompt = """Critique the pros and cons of each plan based on the following guidelines, prioritizing thoroughness and correctness over potential performance overhead: 
- Correctness: The code change should fully address the original issue or requirement without introducing new bugs, security vulnerabilities, or performance problems. Follow defensive programming practices, such as avoiding implicit assumptions, validating inputs, and handling edge cases. Consider the potential impact on all relevant data structures and ensure the solution maintains data integrity and consistency. Thoroughness is a top priority. 
- Backwards Compatibility: When possible, avoid breaking changes to public APIs, data formats, or behaviors that existing code depends on. 
- Clarity: The code change should be readable, well-structured, and easy for other developers to understand and maintain. Follow existing conventions and style guides, and include documentation and comments for complex or non-obvious logic. 
- Simplicity: Strive for a solution that is as simple as possible while still being complete and correct. Favor straightforward and easily understandable code. Performance overhead should not be a factor in evaluating simplicity. 
- Integration: Assess how well the change fits with the overall architecture and design of the system. Avoid tightly coupling components or introducing new dependencies that could complicate future development or deployment. After evaluating the plans against these criteria, select the one that provides the most thorough and correct solution within the specific context and constraints of the project. Prioritize long-term maintainability and architectural integrity.

Respond using the following XML format:

<final_plan>
[Insert the final plan here, including any modifications or improvements based on the feedback and dialogue. Explain how the plan aligns with the guidelines and why it was chosen over the alternatives.]
</final_plan>

Here is an example response format:

<final_plan>
<modify file="example.py">
[Example instructions here]
</modify>
...
<modify file="anotherexamplefile.py">
[More example instructions here]
</modify>
[Your explanation of why this plan was chosen and how it aligns with the guidelines and any modications made to this plan]
</final_plan>"""

context_files_to_change_system_prompt = """You are an AI assistant helping an intern plan the resolution to a GitHub issue. Code files, a description of the issue, and relevant parts of the codebase have been provided. List all of the relevant files to reference while making changes, one per line."""

context_files_to_change_prompt = """Your job is to write two high quality approaches for an intern to help resolve a user's GitHub issue. 

Follow the below steps:
1. Identify the root cause of the issue by referencing specific code entities in the relevant files. (1 paragraph)

2. Plan two possible solutions to the user's request, prioritizing changes that use different files in the codebase. List them below as follows:
    - Plan 1: The most likely solution to the issue. Reference the provided code files, summaries, entity names, and necessary files/directories.
    - Plan 2: The second most likely solution to the issue. Reference the provided code files, summaries, entity names, and necessary files/directories.

3. List all tests that may need to be added or updated to validate the changes given the two approaches. Follow the following format:
    - Plan 1:
        - File path 1: Detailed description of functionality we need to test in file path 1
            a. Identify where the functionality will take place.
            b. Check the <imports> section to find the most relevant test that imports file path 1 to identify where the existing tests for this are located.
        - File path 2: Detailed description of functionality we need to test in file path 2
            a. Identify where the functionality will take place.
            b. Check the <imports> section to find the most relevant test that imports file path 2 to identify where the existing tests for this are located.
        [additional files as needed]
    - Plan 2:
        - File path 1: Detailed description of functionality we need to test in file path 1
            a. Identify where the functionality will take place.
            b. Check the <imports> section to find the most relevant test that imports file path 1 to identify where the existing tests for this are located.
        - File path 2: Detailed description of functionality we need to test in file path 2
            a. Identify where the functionality will take place.
            b. Check the <imports> section to find the most relevant test that imports file path 2 to identify where the existing tests for this are located.
        [additional files as needed]

4a. List all files, including tests, that may need to be modified to resolve the issue given the two approaches.

- These files must be formatted in <relevant_files> tags like so:
<relevant_files>
file_path_1
file_path_2
...
</relevant_files>

4b. List all relevant read-only files from the provided set given the two approaches. Only include files that are CRUCIAL to reference while making changes in other files.

- These files must be formatted in <read_only_files> tags like so:
<read_only_files>
file_path_1
file_path_2
...
[additional files as needed, 1-5 files]
</read_only_files>

Generate two different plans to address the user issue. The best plan will be chosen later."""

extract_files_to_change_prompt = """\
# Task:
Create a plan that resolves the user's query and ONLY the user's query under "Issue Title" and "Issue Description", providing your response in the below format:
<contextual_request_analysis>
Review each function of each relevant_snippet and analyze the user request to determine if this change should use the refactor or unit test tools.
The refactor tool performs code transformations in a single file without making other logical changes. Determine the function(s) that are too long and should have it's individual parts extracted.
The unit test tool creates or edits unit tests for a given file. Determine all functions that should be unit tested.
</contextual_request_analysis>

<use_tools>
True/False
</use_tools>

If use_tools is True, then generate a plan to use the given tools in this format:
* Make sure destination_module refers to a python module and not a path.

<refactor file="file_path_1" destination_module="destination_module" relevant_files="space-separated list of ALL files relevant for modifying file_path_1">
</refactor>
<test file="file_path_2" source_file="file_path_to_test" relevant_files="space-separated list of ALL files relevant for modifying file_path_2">
* Unit tests for the file_path_to_test, to be written in file_path_2.
* Exact and descriptive instructions for the tests to be created or modified.
...
</test>"""

refactor_files_to_change_prompt = """\
Reference and analyze the snippets, repo, and issue to break down the requested change and propose a plan that addresses the user's request.

Provide a plan to solve the issue, following these rules:
* You may only create new files, extract snippets into functions, relocate functions, or modify existing files.
* Include the full path (e.g. src/main.py and not just main.py), using the repo_tree for reference.
* Be concrete with instructions and do not write "identify x" or "ensure y is done". Simply write "add x" or "change y to z".

You MUST follow the following format:

# Contextual Request Analysis:
<contextual_request_analysis>
* Outline the ideal plan that solves the user request by referencing the snippets and any other necessary files/directories.
* Describe each <create>, <modify>, <extract>, and <relocate> section in the following plan and why it will be needed. Make sure the ordering is correct.
...
</contextual_request_analysis>

# Plan:
<plan>
<create file="file_path_1" relevant_files="space-separated list of ALL files relevant for creating file_path_1">
* Exact instructions for creating the new file needed to solve the issue
* Include references to all files, imports and entity names
...
</create>
...

<extract file="file_path_2" relevant_files="space-separated list of ALL files relevant for modifying file_path_2">
* Extracts lines of code from a function into a new standalone function.
* Only extract lines that reduce the overall nesting or complexity of the code.
...
</extract>
...

<relocate file="file_path_3" new_file_path="new_file_path" handle_references="True">
* This will move a function or variable from file_path_3 into another file while automatically resolving everything. If you use this block do not add other modifications related to imports, references, or function calls.
</relocate>
...

<modify file="file_path_4" relevant_files="space-separated list of ALL files relevant for modifying file_path_4">
* Modifies files by making less than 30-line changes. Be exact and mention references to all files, imports and entity names.
* Use detailed, natural language instructions on what to modify regarding business logic, and reference files to import.
* Be concrete with instructions and do not write "identify x" or "ensure y is done". Simply write "add x" or "change y to z".
* You may modify the same file multiple times.
...
</modify>
...

</plan>"""

sandbox_files_to_change_prompt = """\
Analyze the snippets, repo, and issue to break down the requested problem or feature. Then propose a high-quality plan that completely fixes the CI/CD run.

Provide a list of ALL of the files we should modify, abiding by the following:
* You may only create and modify files.
* Including the FULL path, e.g. src/main.py and not just main.py, using the repo_tree for reference.
* Use detailed, natural language instructions on what to modify regarding business logic, and reference files to import.
* Be concrete with instructions and do not write "check for x" or "ensure y is done". Simply write "add x" or "change y to z".
* If the tests fail you should typically fix the tests and not the source code.

You MUST follow the following format with the final output in XML tags:

<analysis_and_plan>
Whether the change was caused by the user's change or not. If not, then leave the plan empty.
Otherwise, determine why the CI/CD run failed and the root cause. Determine the MINIMAL amount of changes to fix, with reference to entities, in the following format:

<minimal_changes>
* Change x: file to make the change
* Change y: file to make the change
...
</minimal_changes>
</analysis_and_plan>

<plan>
<create file="file_path_1" relevant_files="space-separated list of ALL files relevant for creating file_path_1">
Outline of additions in concise natural language of what needs to be implemented in this file, referencing to external and imported libraries and business logic.
</create>

<modify file="file_path_2" relevant_files="space-separated list of ALL files relevant for modifying file_path_2">
Outline of modifications in natural language (no code), referencing entities, and what type of patterns to look for, such as all occurrences of a variable or function call.
Do not make this XML block if no changes are needed.
</modify>
...

</plan>"""

subissues_prompt = """
Think step-by-step to break down the requested problem into sub-issues each of equally sized non-trivial changes. The sub-issue should be a small, self-contained, and independent part of the problem, and should partition the files to be changed.
You MUST follow the following format with the final output in XML tags:

Root cause:
Identify the root cause of this issue and a minimum plan to address this issue concisely in two sentences.


Step-by-step thoughts with explanations:
* Concise imperative thoughts
* No conjunctions
...

<plan>
<issue title="title_1">
* In file_path_1, do a
* In file_path_1, do b
...
* In file_path_2, do c
* In file_path_2, do d
...
</issue>

<issue title="title_2">
* In file_path_1, do a
* In file_path_1, do b
...
* In file_path_2, do c
* In file_path_2, do d
...
</issue>

...
</plan>"""

chunking_prompt = """
We are handling this file in chunks. You have been provided a section of the code.
Any lines that you do not see will be handled, so trust that the imports are managed and any other issues are taken care of.
If you see code that should be modified, please modify it. The changes may not need to be in this chunk, do not make any changes."""

modify_file_hallucination_prompt = [
    {
        "content": """File Name: (non-existent example)
<old_file>
example = True
if example:
    x = 1 # comment
    print("hello")
    x = 2

class Example:
    foo: int = 1

    def func():
        a = 3

</old_file>

---

Code Planning:
Step-by-step thoughts with explanations:
* Thought 1
* Thought 2
...

Commit message: "feat/fix: the commit message"

Detailed plan of modifications:
* Modification 1
* Modification 2
...

Code Generation:

```
Generate a diff based on the given plan using the search and replace pairs in the format below.
* Always prefer the least amount of changes possible, but ensure the solution is complete
* Prefer multiple small changes over a single large change.
* NEVER write ellipses anywhere in the diffs. Simply write two diff hunks: one for the beginning and another for the end.
* Always add lines before and after. The ORIGINAL section should be at least 5 lines long.

The format is as follows:

<<<< ORIGINAL
line_before
old_code
line_after
====
line_before
new_code
line_after
>>>> UPDATED
```

Commit message: "the commit message"

Request: "Change hello to goodbye and change 3 to 4". Limit your changes to the request.

Instructions:
1. Complete the Code Planning step
2. Complete the Code Generation step""",
        "role": "user",
        "key": "modify_file_hallucination",
    },
    {
        "content": """Code Planning:
Step-by-step thoughts with explanations:
* We need to print "goodbye" instead of "hello".
* We need to update the value of the variable a from 3 to 4.

Detailed plan of modifications:
* Change the output of the print statement from "hello" to "goodbye" as an example modification.
* I will update the value of a from 3 to 4.

Code Generation:
```
<<<< ORIGINAL
example = True
if example:
    x = 1 # comment
    print("hello")
    x = 2
====
example = True
if example:
    x = 1 # comment
    print("goodbye")
    x = 2
>>>> UPDATED

<<<< ORIGINAL
class Example:
    foo: int = 1

    def func():
        a = 3
====
class Example:
    foo: int = 1

    def func():
        a = 4
>>>> UPDATED
```

Commit message: "Changed goodbye to hello and 3 to 4"\
""",
        "role": "assistant",
        "key": "modify_file_hallucination",
    },
]

# TODO: IMPORTANT: THIS DEPENDS ON THE ABOVE PROMPT, modify_file_hallucination_prompt
modify_file_prompt_3 = """\
File Name: {filename}
<old_file>
{code}
</old_file>

---

User's request:
{instructions}

Limit your changes to the request.

Instructions:
Complete the Code Planning step and Code Modification step.
Remember to NOT write ellipses, code things out in full, and use multiple small hunks.\
"""

modify_recreate_file_prompt_3 = """\
File Name: {filename}
<old_file>
{code}
</old_file>

---

User's request:
{instructions}

Limit your changes to the request.

Format:
```
<new_file>
{{new file content}}
</new_file>
```

Instructions:
1. Complete the Code Planning step
2. Complete the Code Modification step, remembering to NOT write ellipses, write complete functions, and use multiple small hunks where possible."""

modify_file_system_message = """\
You are a brilliant and meticulous engineer assigned to write code for the file to address a Github issue. When you write code, the code works on the first try and is syntactically perfect and complete. You have the utmost care for your code, so you do not make mistakes and every function and class will be fully implemented. Take into account the current repository's language, frameworks, and dependencies. You always follow up each code planning session with a code modification.

When you modify code:
* Always prefer the least amount of changes possible, but ensure the solution is complete.
* Prefer multiple small changes over a single large change.
* Do not edit the same parts multiple times.
* Make sure to add additional lines before and after the original and updated code to disambiguate code when replacing repetitive sections.
* NEVER write ellipses anywhere in the diffs. Simply write two diff hunks: one for the beginning and another for the end.

Respond in the following format. Both the Code Planning and Code Modification steps are required.

### Format ###

## Code Planning:

Thoughts and detailed plan:
1.
2.
3.
...

Commit message: "feat/fix: the commit message"

## Code Modification:

Generated diff hunks based on the given plan using the search and replace pairs in the format below.
```
The first hunk's description

<<<< ORIGINAL
{exact copy of lines you would like to change}
====
{updated lines}
>>>> UPDATED

The second hunk's description

<<<< ORIGINAL
second line before
first line before
old code
first line after
second line after
====
second line before
first line before
new code
first line after
second line after
>>>> UPDATED
```"""

RECREATE_LINE_LENGTH = -1

modify_file_prompt_4 = """\
File Name: {filename}

<file>
{code}
</file>

---

Modify the file by responding in the following format:

Code Planning:

Step-by-step thoughts with explanations:
* Thought 1
* Thought 2
...

Detailed plan of modifications:
* Replace x with y
* Add a foo method to bar
...

Code Modification:

```
Generate a diff based on the given instructions using the search and replace pairs in the following format:

<<<< ORIGINAL
second line before
first line before
old code
first line after
second line after
====
second line before
first line before
new code
first line after
second line after
>>>> UPDATED
```

Commit message: "the commit message"

The user's request is:
{instructions}

Instructions:
1. Complete the Code Planning step
2. Complete the Code Modification step
"""

rewrite_file_system_prompt = "You are a brilliant and meticulous engineer assigned to write code for the file to address a Github issue. When you write code, the code works on the first try and is syntactically perfect and complete. You have the utmost care for your code, so you do not make mistakes and every function and class will be fully implemented. Take into account the current repository's language, frameworks, and dependencies."

rewrite_file_prompt = """\
File Name: {filename}
<old_file>
{code}
</old_file>

---

User's request:
{instructions}

Limit your changes to the request.

Rewrite the following section from the old_file to handle this request.

<section>

{section}

</section>

Think step-by-step on what to modify, then wrap the final answer in the brackets <section></section> XML tags. Only rewrite the section and do not close hanging parentheses and tags.\
"""

sandbox_code_repair_modify_prompt_2 = """
File Name: {filename}

<file>
{code}
</file>

---

Above is the code that was written by an inexperienced programmer, and contain errors such as syntax errors, linting erors and type-checking errors. The CI pipeline returned the following logs:

stdout:
```
{stdout}
```

stderr
```
{stderr}
```

Respond in the following format:

Code Planning

Determine the following in code planning:
1. Are there any syntax errors? Look through the file to find all syntax errors.
2. Are there basic linting errors, like undefined variables, undefined members or type errors?
3. Are there incorrect imports and exports?
4. Are there any other errors not listed above?

Determine whether changes are necessary based on the errors (ignore warnings).

Code Modification:

Generate a diff based on the given plan using the search and replace pairs in the format below.
* Always prefer the least amount of changes possible, but ensure the solution is complete
* Prefer multiple small changes over a single large change.
* NEVER write ellipses anywhere in the diffs. Simply write two diff hunks: one for the beginning and another for the end.
* DO NOT modify the same section multiple times.
* Always add lines before and after. The ORIGINAL section should be at least 5 lines long.
* Restrict the changes to fixing the errors from the logs.

The format is as follows:

```
<<<< ORIGINAL
second line before
first line before
old code of first hunk
first line after
second line after
====
second line before
first line before
new code of first hunk
first line after
second line after
>>>> UPDATED

<<<< ORIGINAL
second line before
first line before
old code of second hunk
first line after
second line after
====
second line before
first line before
new code of second hunk
first line after
second line after
>>>> UPDATED
```

Commit message: "the commit message"

Instructions:
1. Complete the Code Planning step
2. Complete the Code Modification step
"""

pr_code_prompt = ""  # TODO: deprecate this

pull_request_prompt = """Now, create a PR for your changes. Be concise but cover all of the changes that were made.
For the pr_content, add two sections, description and summary.
Use GitHub markdown in the following format:

pr_title = "..."
branch = "..."
pr_content = \"\"\"
...
...
\"\"\""""

summarize_system_prompt = """
You are an engineer assigned to helping summarize code instructions and code changes.
"""

user_file_change_summarize_prompt = """
Summarize the given instructions for making changes in a pull request.
Code Instructions:
{message_content}
"""

assistant_file_change_summarize_prompt = """
Please summarize the following file using the file stubs.
Be sure to repeat each method signature and docstring. You may also add additional comments to the docstring.
Do not repeat the code in the file stubs.
Code Changes:
{message_content}
"""

code_repair_check_system_prompt = """\
You are a genius trained for validating code.
You will be given two pieces of code marked by xml tags. The code inside <diff></diff> is the changes applied to create user_code, and the code inside <user_code></user_code> is the final product.
Our goal is to validate if the final code is valid. This means there are no undefined variables, no syntax errors, has no unimplemented functions (e.g. pass's, comments saying "rest of code") and the code runs.
"""

code_repair_check_prompt = """\
This is the diff that was applied to create user_code. Only make changes to code in user_code if the code was affected by the diff.

This is the user_code.
<user_code>
{user_code}
</user_code>

Reply in the following format:

Step-by-step thoughts with explanations:
1. No syntax errors: True/False
2. No undefined variables: True/False
3. No unimplemented functions: True/False
4. Code runs: True/False

<valid>True</valid> or <valid>False</valid>
"""

code_repair_system_prompt = """\
You are a genius trained for code stitching.
You will be given two pieces of code marked by xml tags. The code inside <diff></diff> is the changes applied to create user_code, and the code inside <user_code></user_code> is the final product. The intention was to implement a change described as {feature}.
Our goal is to return a working version of user_code that follows {feature}. We should follow the instructions and make as few edits as possible.
"""

code_repair_prompt = """\
This is the diff that was applied to create user_code. Only make changes to code in user_code if the code was affected by the diff.

This is the user_code.
<user_code>
{user_code}
</user_code>

Instructions:
* Do not modify comments, docstrings, or whitespace.

The only operations you may perform are:
1. Indenting or dedenting code in user_code. This code MUST be code that was modified by the diff.
2. Adding or deduplicating code in user_code. This code MUST be code that was modified by the diff.

Return the working user_code without xml tags. All of the text you return will be placed in the file.
"""

doc_query_rewriter_system_prompt = """\
You must rewrite the user's github issue to leverage the docs. In this case we want to look at {package}. It's used for: {description}. Using the github issue, write a search query that searches for the potential answer using the documentation. This query will be sent to a documentation search engine with vector and lexical based indexing. Make this query contain keywords relevant to the {package} documentation.
"""

doc_query_rewriter_prompt = """\
This is the issue:
{issue}

Write a comprehensive search query for the answer.
"""

should_edit_code_system_prompt = """\
We are processing a large file and trying to make code changes to it.
The file is definitely relevant, but the section we observe may not be relevant.
Your job is to determine whether the instructions are referring to the given section of the file.
"""

should_edit_code_prompt = """\
Here are the instructions to change the code in the file:
{problem_description}
Here is the code snippet from the file:
{code_snippet}

To determine whether the instructions are referring to this section of the file, respond in the following format:
1. Step-by-step thoughts with explanations:
* Thought 1 - Explanation 1
* Thought 2 - Explanation 2
...
2. Planning:
* Is the code relevant?
* If so, what is the relevant part of the code?
* If not, what is the reason?

3. In the last line of your response, write either <relevant>True</relevant> or <relevant>False</relevant>.
"""

slow_mode_system_prompt = """You are a brilliant and meticulous software architect. Your job is to take in the user's GitHub issue and the relevant context from their repository to:
1. Gather more code snippets using a code search engine.
2. Expand upon the plan to address the issue."""

generate_plan_and_queries_prompt = """Think step-by-step to break down the requested problem or feature, and write up to three queries for the code search engine. These queries should find relevant code that is not already mentioned in the existing snippets. They should all mention different files and subtasks of the initial issue, avoid duplicates.
Then add more instructions that build on the user's instructions. These instructions should help plan how to solve the issue.
* The code search engine is based on semantic similarity. Ask questions that involve code snippets, function references, or mention relevant file paths.
* The user's instructions should be treated as the source of truth, but sometimes the user will not mention the entire context. In that case, you should add the missing context.
* Gather files that are relevant, including dependencies and similar files in the codebase. For example, if the user asked to write tests, look at similar tests.

You MUST follow the following format delimited with XML tags:

Step-by-step thoughts with explanations:
* Thought 1 - Explanation 1
* Thought 2 - Explanation 2
...

<queries>
* query 1
* query 2
* query 3
</queries>

<additional_instructions>
* additional instructions to be appended to the user's instructions
</additional_instructions>
"""

external_search_system_prompt = (
    "You are an expert at summarizing content from pages that are relevant to a query."
    " You will be given a page and asked to summarize it."
)

external_search_prompt = """\
Here is the page metadata:
```
{page_metadata}
```

The user is attempting to solve the following problem:
\'\'\'
{problem}
\'\'\'

Provide a summary of the page relevant to the problem, including all code snippets.
"""


docs_qa_system_prompt = """You are an expert at summarizing documentation for programming-related to help the user solve the problem. You will be given a question and relevant snippets of documentation, and be asked to provide a summary of relevant snippets for solving the problem."""
docs_qa_user_prompt = """Here are the relevant documentation snippets:
{snippets}

The user is attempting to solve the following problem:
{problem}
"""

linting_new_file_prompt = """
<new_file>
{code}
</new_file>
"""

linting_modify_prompt = """Code Planning:
Step-by-step thoughts with explanations:
* Thought 1
* Thought 2
...

Detailed plan of modifications:
* Modification 1
* Modification 2
...

Code Generation:

```
Generate a diff based on the given plan using the search and replace pairs in the format below.
* Always prefer the least amount of changes possible
* Prefer many small edits over few large edits
* Always add lines before and after. The ORIGINAL section should be at least 5 lines long.

The linter returned the following logs:
<linter_logs>
{logs}
</linter_logs>

Modify your created file. Note if no changes are needed.

---

The format is as follows:

<<<< ORIGINAL
====
>>>> UPDATED

Instructions:
1. Complete the Code Planning step
2. Complete the Code Generation step"""

summarize_snippet_system_prompt = """You are a technical writer. Summarize code for an engineer. Be concise but detailed. Mention all entities implicitly. Never say "the code does x", just say "x". Keep it within 30 lines.

E.g: If `issue_comment` is None, set `issue_comment` to `current_issue.create_comment(first_comment)`, otherwise edit comment via `issue_comment.edit(first_comment)`"""

summarize_snippet_prompt = """# Code
```
{code}
```

# Repo Metadata
{metadata}

# Issue
{issue}

# Instructions
Losslessly summarize the code in a ordered list for an engineer to search for relevant code to solve the above GitHub issue."""


use_chunking_message = """\
Respond with a list of the MINIMUM sections that should be modified. To insert code after a function, fetch the last few lines of the function."""

dont_use_chunking_message = """\
Respond with a list of the MINIMUM sections that should be modified. To insert code after a function, fetch the last few lines of the function."""
