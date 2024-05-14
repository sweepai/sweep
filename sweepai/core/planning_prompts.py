issue_excerpt_system_prompt = """You are a tech lead helping to break down a GitHub issue for an intern to solve. Segment the GitHub issue to identify every single one of the user's requests. Be complete. The changes should be atomic."""

# TODO: 2 paragraphs
# the current issue analysis is heavily optimized, i'd like to try removing step d though
issue_excerpt_prompt = """\
Segment the GitHub issue to identify every single one of the user's requests. Be complete. The changes should be atomic.

Respond in the following format:
<issue_excerpts>
<issue_excerpt>
A very short substring from the user's issue. This should correspond to a specific change in the codebase.
</issue_excerpt>
</issue_excerpts>"""


files_to_change_system_prompt = """You are an AI assistant helping an intern write code to resolve a GitHub issue. The user will provide code files, a description of the issue, and relevant parts of the codebase.
Your role is to analyze the issue and codebase, then provide a clear, step-by-step plan the intern can follow to make the necessary code changes to resolve the issue. Reference specific files, functions, variables and code files in your plan. Organize the steps logically and break them into small, manageable tasks.
Prioritize using existing code and functions to make efficient and maintainable changes. Ensure your suggestions fully resolve the issue.

Take these steps:
1. Issue Analysis: Analyze the issue and codebase to understand the problem. This section will vary in verbosity depending on the complexity of the issue, but each section should be at least 1 paragraph long.

2. Plan: Create a detailed plan for the intern to follow, including all necessary changes to resolve the issue.
    - When modifying code you MUST do the following:
        - Modify step 1. Copy the original code in <original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are not permitted.
        - Modify step 2. Write the new code in <new_code> tags, specifying necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>."""

files_to_change_prompt = """Your job is to write a high quality, detailed, step-by-step plan for an intern to help resolve a user's GitHub issue.

You will analyze the provided code files, repository, and GitHub issue to understand the requested change. Create a step-by-step plan for an intern to fully resolve the user's GitHub issue. The plan should utilize the relevant code files and utility modules provided. Give detailed instructions for updating the code logic, as the intern is unfamiliar with the codebase.

Guidelines:
- Always include the full file path and reference the provided files 
- Provide clear instructions for updating the code, specifying necessary imports
- Be specific and direct, using the phrases "add", "replace", and "remove".
- Reference relevant type definitions, interfaces, and schemas 
- Ensure your plan is complete and covers all necessary changes to fully resolve the issue
- Suggest high-quality, safe, maintainable, efficient and backwards compatible changes
- Prioritize using existing code and utility methods to minimize writing new code
- Break the task into small steps, with each <create> or <modify> section for each logical code block worth of change. Use multiple <modify> blocks for the same file if there are multiple distinct changes to make in that file.
- To remove code, replace it with empty <new_code> tags.

Please use the following XML format for your response:

# 1. Issue Analysis:
<issue_analysis>
a. Identify potential root causes of the issue by referencing specific code entities in the relevant files. Then, select which of the root causes the user is most likely to be interested in resolving based on the current state of the codebase. (write at least 1 paragraph)

b. Detail ALL of the changes that need to be made to the codebase (excluding tests) to resolve the user request. For each of the excerpts here write a detailed set of code changes spanning at least one change, with possibly more depending on the preceding excerpt. Be specific and direct, using the phrases "add", "replace", and "remove". Be complete and precise. You must cover ALL changes that are required per excerpt.
{issue_excerpts}

Reference the provided code files, summaries, entity names, and necessary files/directories. The format should be:
<issue_and_proposed_changes>
<issue_excerpt>
...
</excerpt_from_issue>
<proposed_changes>
1. For each of the excerpts here write a detailed set of code changes spanning at least one change, with more depending on the preceding excerpt. This code change should describe exactly what to do, referencing specific code entities in the relevant files.
...
</proposed_changes>
</issue_and_proposed_changes>

c. Detail ALL changes that do not correspond to an excerpt from the user's issue. These changes should be necessary to resolve the issue but are not explicitly mentioned in the user's request. This code change should describe exactly what to do, referencing specific code entities in the relevant files. (optional)
</issue_analysis>

# 2. Plan:
<plan>  
<create file="file_path_1">
Instructions for creating the new file. Reference imports and entity names. Include relevant type definitions, interfaces, and schemas.
</create>
[additional creates]

<modify file="file_path_2"> 
Instructions for modifying one section of the file. A description of the changes you are going to make.

1. Reference the original code in <original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are not permitted. This block must NOT be empty. The referenced original code span should be just enough to cover the change, with 10 extra lines above and below for context.

2. Write the new code in <new_code> tags, with the desired changes incorporated. Specify necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>. This block MUST be different from the <original_code>.

If imports are needed, they should be in a separate <modify> block. Use multiple <modify> blocks for the same file to separate distinct changes.
</modify>

<modify file="file_path_2">
Instructions for modifying a different section of the same file. A description of the changes you are going to make.

1. Reference the original code in <original_code> tags, copying them VERBATIM from the file. Do NOT paraphrase or abbreviate the source code. Placeholder comments like "# existing code" are not permitted. This block must NOT be empty. The referenced original code span should be just enough to cover the change, with 10 extra lines above and below for context.

2. Write the new code in <new_code> tags, with the desired changes incorporated. Specify necessary imports and referencing relevant type definitions, interfaces, and schemas. BE EXACT as this code will replace the mentioned <original_code>. This block MUST be different from the <original_code>.

Use multiple <modify> blocks for the same file to separate distinct changes.
</modify>

[additional modifies as needed, for the same file or different files]
</plan>"""