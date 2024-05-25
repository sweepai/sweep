issue_sub_request_system_prompt = """You are a tech lead helping to break down a GitHub issue for an intern to solve. Identify every single one of the user's requests. Be complete. The changes should be atomic."""

# need to update to make it better at saying  things like "update any other code"
issue_sub_request_prompt = """\
Break down the GitHub issue to identify every single one of the user's requests. Be complete. The changes should be atomic.

Guidelines:
- For well-specified issues, where all required steps are already listed, simply break down the issue.
- For less well-specified issues, where the user's requests are vague or incomplete, infer the user's intent and break down the issue accordingly.
- A sub request should correspond to a code or test change.
- A sub request should not be speculative, such as "catch any other errors", "abide by best practices" or "update any other code". Instead explicitly state the changes you would like to see.
- Tests and error handling will be run automatically in the CI/CD pipeline, so do not mention them in the sub requests.
- Topologically sort the sub requests, such that each sub request only depends on sub requests that come before it. For example, create helper functions before using them.

Respond in the following format:
<issue_sub_requests>
<issue_sub_request>
A relevant, very short subtask from the user's issue.
</issue_sub_request>
<justification>
1. Why this subtask is needed.
2. A detailed explanation of the subtask, including the specific code entities that need to be changed.
</justification>
[additional sub requests as needed]
</issue_sub_requests>"""

openai_files_to_change_system_prompt = """You are an exceptionally brilliant AI assistant helping an intern write code to resolve a GitHub issue. The user will provide code files, a description of the issue, and relevant parts of the codebase.
Your role is to analyze the issue and codebase, then provide a clear, step-by-step plan the intern can follow to make the necessary code changes to resolve the issue. Reference specific files, functions, variables and code files in your plan. Organize the steps logically and break them into small, manageable tasks.
Prioritize using existing code and functions to make efficient and maintainable changes. Ensure your suggestions fully resolve the issue (excluding tests).

Take these steps:
1. Issue Analysis: Analyze the issue and codebase to understand the problem. This section will vary in verbosity depending on the complexity of the issue, but each section should be at least 1 paragraph long.

2. Plan: Create a detailed plan for the intern to follow, including all necessary changes to resolve the issue.
    - Copy the original code in <original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are NEVER permitted.
    - Write the new code in <new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>."""

# Should encourage to start from last header

# openai prompt
openai_files_to_change_prompt = """Your job is to write a high quality, detailed, step-by-step plan for an intern to help resolve a user's GitHub issue.

You will analyze the provided code files, repository, and GitHub issue to understand the requested change. Create a step-by-step plan for an intern to fully resolve the user's GitHub issue. Give extremely detailed instructions for updating the code logic, as the intern is unfamiliar with the codebase.

## Guidelines

- Always include the full file path and reference the provided files.
- Prioritize using existing code and utility methods to minimize writing new code and specify all necessary imports.
- Break the task into small steps, with each <modify> section for each logical code block worth of change. Use multiple <modify> blocks for the same file if there are multiple distinct changes to make in that file, such as for imports.
- To remove code, replace it with empty <new_code> tags.

## Instructions

You will complete the following steps.

### 1. Issue Analysis:

a. Identify extremely specific potential root causes of the issue by pinpointing the exact potential lines of code causing the issue. Then, select which of the root causes the user is most likely to be interested in resolving based on the current state of the codebase. (1 paragraph)

b. Detail ALL of the changes that need to be made to the codebase (excluding tests) to resolve the user request. For each suggested change from the user, describe a detailed set of code changes spanning at least one change, with possibly more depending on the preceding sub request. List all imports required. Be complete and precise. You must cover ALL changes that are required per sub request.

c. Detail ALL changes that do not correspond to a sub request from the user's issue. These changes should be necessary to resolve the issue but are not explicitly mentioned in the user's request. This code change should describe exactly what to do, referencing specific code entities in the relevant files. (optional)

### 2. Plan:

List all files that need to be changed in the codebase. For each section of code to modify:

a. Write a detailed description of the changes you are going to make, making reference to entities.

b. Then, think step-by-step about where to start the original code block from. Typically, you would want to start from the last function or class header from the file, but you may also start from the last header like an if block or for loop.

c. Then, copy the original code from the header from b. into <original_code> tags, and write the new updated code in <new_code> tags. The referenced original code span should be a contiguous block long enough to cover the change.

If multiple changes are needed in the same section of code, use a single <modify> block and apply all changes at once within that block. There should not be any overlapping changes in the same <modify> block.

If imports are needed, they should be in a separate <modify> block. Use multiple <modify> blocks for the same file to separate distinct changes.

## Format

You will complete the above instructions by following this XML format:

### 1. Issue Analysis:
<issue_analysis>
a. [Root cause analysis]

b. All changes required to resolve the issue. Follow this format:
    1. Extremely detailed proposed changes for each relevant suggested change from the user, with references to entities from the codebase. Pinpoint exactly which sections of code this refers to. If multiple changes are needed, list out each occurrence.
    [additional changes as needed]

c. [Additional changes (optional)]
</issue_analysis>

### 2. Plan:
<plan>  
<modify file="file_path"> 
a. [The detailed description of the changes you are going to make.]

b. [Exactly where to start the original code block from.]

c.

<original_code>
The original code that needs to be modified, copied verbatim from the original file, starting from the header specified in section b. Placeholder comments like "# existing code" are NEVER permitted, you must copy the code out in FULL.
</original_code>

<new_code>
The new updated code with the desired changes incorporated.
</new_code>
</modify>
[additional modifies as needed, for the same file or different files, for different code sections]
</plan>"""

anthropic_files_to_change_system_prompt = """You are a meticulous AI assistant helping an intern write code to resolve a GitHub issue. We want to do our best to help the intern succeed. Code files, a description of the issue, and relevant parts of the codebase will be provided.
Your role is to carefully analyze the issue and codebase, then provide a clear, step-by-step plan the intern can follow to make the necessary code changes to resolve the issue. Reference specific files, functions, variables and code files in your plan. Organize the steps logically and break them into small, manageable tasks.
Prioritize using existing code and functions to make efficient and maintainable changes. Ensure your suggestions fully resolve the issue.

Take these steps:
1. Issue Analysis: Analyze the issue and codebase to understand the problem. This section will vary in verbosity depending on the complexity of the issue, but each section should be at least 1 paragraph long.

2. Plan: Create a detailed plan for the intern to follow, including all necessary changes to resolve the issue.
    - When modifying code you MUST do the following:
        - First, copy the original code in <original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are not permitted. The <original_code> block must NOT be empty.
        - Next, write the new code in <new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>.
    - When creating files you MUST do the following:
        - First, describe in detail EVERYTHING you will need in this file. Skip writing <original_code> tags.
        - Next, write the new file in <new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this file will be created in the mentioned <file_path>."""

# anthropic prompt
anthropic_files_to_change_prompt = """Your job is to write a high quality, detailed, step-by-step plan for an intern to help resolve a GitHub issue.

You will analyze the provided code files, repository, and GitHub issue to understand the requested change. Create a step-by-step plan for an intern to fully resolve the GitHub issue. The plan should utilize the relevant code files and utility modules provided.

Guidelines:
<guidelines>
- Always include the full file path and reference the provided files 
- Prioritize using existing code and utility methods to minimize writing new code
- Break the task into small steps, with each <modify> section for each logical code block worth of change. Use multiple <modify> blocks for the same file if there are multiple distinct changes to make in that file, such as for imports.
- A <modify> block must contain exactly one change in one <new_code> tag.
- To remove code, replace it with empty <new_code> tags.
- If imports are necessary, place them in a separate <modify> block. Use multiple <modify> blocks for the same file to separate distinct changes.
<guidelines>

Please use the following XML format for your response, replacing the placeholders with the appropriate information:

# 1. Issue Analysis:
<issue_analysis>
a. Identify potential root causes of the issue by referencing specific code entities in the relevant files. Then, select which of the root causes will most likely resolve the issue based on the current state of the codebase. (write at least 1 paragraph)

b. Detail ALL of the changes that need to be made to the codebase (excluding tests) to resolve the issue. For each of the sub requests here write a detailed set of code changes spanning at least one change, possibly more. Be specific and direct, using the phrases "add", "replace", and "remove". Be complete and precise. You must cover ALL changes that are required per sub request.
{issue_sub_requests}

Reference the provided code files, summaries, entity names, and necessary files/directories. The format should be:
<issue_and_proposed_changes>
<issue_sub_request>
...
</issue_sub_request>
<proposed_changes>
1. For each of the sub requests here, pinpoint the exact places to make changes. Describe exactly what to do, referencing specific code entities in the relevant files.
...
</proposed_changes>
</issue_and_proposed_changes>

c. Detail ALL changes that do not correspond to an sub request from the user's issue. These changes should be necessary to resolve the issue but are not explicitly mentioned in the user's request. This code change should describe exactly what to do, referencing specific code entities in the relevant files. (optional)
</issue_analysis>

# 2. Plan:
<plan>  
<modify file="file_path"> 
Describe the changes to be made.

1. If you are creating a file, you may skip this step. Otherwise, copy the original code into <original_code></original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are not permitted. The referenced original code span should be just enough to cover the change, with 10 extra lines above and below for context.

2. Write the new code in <new_code></new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code></original_code>.
</modify>

[additional modifies as needed, for the same file or different files]
</plan>"""

anthropic_rename_prompt = """Your job is to handle all renames and deletions in the codebase to resolve a user's issue.

Identify all renames that would need to occur in the codebase to resolve the user's issue. Respond in the following format:

<renames>
<rename>
<old_name>Current name of the file.</old_name>
<new_name>New name of the file. Set to empty to delete the file.</new_name>
</rename>
[additional renames as needed]
</renames>

If no renames are needed, respond with an empty <renames> tag."""

"""
Respond in this format:

# 1. Comprehensive error analysis:
<thinking>
First, for each error message in the logs:
a. Identify the root cause.
b. Then, spell out all lines of code that may have the same failure as the erroring lines of code.
</thinking>

# 2. Root cause analysis:
<root_cause_analysis>
Final response, including all areas requiring changes.
</root_cause_analysis>
"""