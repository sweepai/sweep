"""
List of common prompts used across the codebase.
"""

# Following two should be fused
system_message_prompt = "Your name is Sweep bot. You are a brilliant and meticulous engineer assigned to write code for the following Github issue. When you write code, the code works on the first try and is formatted perfectly. You have the utmost care for the code that you write, so you do not make mistakes. Take into account the current repository's language, frameworks, and dependencies."

repo_description_prefix_prompt = "This is the repository description provided by the user. Keep this in mind:"

human_message_prompt = [
{'role': 'assistant', 'content': 'Examining repo...'},
{'role': 'user', 'content': """<relevant_snippets_in_repo>
{relevant_snippets}
</relevant_snippets_in_repo>""", 'key': 'relevant_snippets'},
{'role': 'user', 'content': """<relevant_paths_in_repo>
{relevant_directories}
</relevant_paths_in_repo>""", 'key': 'relevant_directories'},
{'role': 'user', 'content': """<repo_tree>
{tree}
</repo_tree>""", 'key': 'relevant_tree'},
{'role': 'user', 'content':
"""# Repo & Issue Metadata
Repo: {repo_name}: {repo_description}
Issue Url: {issue_url}
Username: {username}
Issue Title: {title}
Issue Description: {description}"""}]

human_message_review_prompt = [
{'role': 'assistant', 'content': 'Reviewing my pull request...'},
{'role': 'user', 'content': """<relevant_snippets_in_repo>
{relevant_snippets}
</relevant_snippets_in_repo>"""},
{'role': 'user', 'content': """<relevant_paths_in_repo>
{relevant_directories}
</relevant_paths_in_repo>"""},
{'role': 'user', 'content': """"<repo_tree>
{tree}
</repo_tree>"""},
{'role': 'user', 'content':
"""These are the file changes.
We have the file_path, and the diffs.
The file_path is the name of the file.
The diffs are the lines changed in the file. <added_lines> indicates those lines were added, <deleted_lines> indicates they were deleted.
Keep in mind that we may see a diff for a deletion and replacement, so don't point those out as issues.
{diffs}"""}]

snippet_replacement = """
In order to address this issue, what required information do you need about the snippets? Only include relevant code that provides you enough detail about the snippets for the problems: 
"{thoughts}"

<contextual_thoughts>
* ...
...
</contextual_thoughts>

<partial_snippet file="...">
[insert relevant segments from thoughts here]
</partial_snippet>

<relevant_paths>
[insert relevant paths from file tree]
</relevant_paths>
"""

diff_section_prompt = """
<file_path>
{diff_file_path}
</file_path>

<file_diffs>
{diffs}
</file_diffs>
"""

review_prompt = """\
I need you to carefully review the code diffs in this pull request. 
The code was written by an inexperienced programmer and may contain accidental deletions, logic errors, unimplemented sections (such as "...") or other issues.
Think step-by-step logically and thoroughly analyze to summarize the diffs per file in the format:

Step-by-step thoughts:
* Lines x1-x2: Summary of the changes (added, deleted, modified, errors, issues) 
* Lines y1-y2: Summary of the changes (added, deleted, modified, errors, issues)
...
<file_summarization>
* file_1 - changes in file_1
* file_1 - more changes in file_1
...
</file_summarization>
"""

review_follow_up_prompt = """\
Here is the next file diff.
Think step-by-step logically and accurately to summarize the diffs per file in the format:
Step-by-step thoughts:
* Lines x1-x2: Summary of the changes (added, deleted, modified, errors, issues) 
* Lines y1-y2: Summary of the changes (added, deleted, modified, errors, issues)
...
<file_summarization>
* file_1 - changes in file_1
* file_1 - more changes in file_1
...
</file_summarization>
"""

final_review_prompt = """\
This were the file summaries you provided:
<file_summaries>
{file_summaries}
</file_summaries>
Given these summaries write a direct and concise GitHub review comment. If there are no changes required, simply say "No changes required."
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
</review_comment>
"""

issue_comment_prompt = """
<comment username="{username}">
{reply}
</comment>
"""

# Prompt for comments
human_message_prompt_comment = [
{'role': 'assistant', 'content': 'Reviewing my pull request...'},
{'role': 'user', 'content':
"""<relevant_snippets_in_repo>
{relevant_snippets}
</relevant_snippets_in_repo>"""},
{'role': 'user', 'content': """<relevant_paths_in_repo>
{relevant_directories}
</relevant_paths_in_repo>"""},
{'role': 'user', 'content': """<repo_tree>
{tree}
</repo_tree>"""},
{'role': 'user', 'content':
"""# Repo, Issue, & PR Metadata
Repo: {repo_name}: {repo_description}
Issue Url: {issue_url}
Username: {username}
Pull Request Title: {title}
Pull Request Description: {description}"""},
{'role': 'user', 'content':
"""These are the file changes.
We have the file_path and the diffs.
The file_path is the name of the file.
The diffs are the lines changed in the file. <added_lines> indicates those lines were added, <deleted_lines> indicates they were deleted.
Keep in mind that we may see a diff for a deletion and replacement, so don't point those out as issues.
{diff}"""},
{'role': 'user', 'content':
"""Please handle the user review comment, taking into account the snippets, paths, tree, pull request title, pull request description, and the file changes.
Sometimes the user may not request changes, don't change anything in that case.
User pull request review: "{comment}" """}]

comment_line_prompt = """\
The user made the review in this file: {pr_file_path}
and on this line: {pr_line}
"""

cot_retrieval_prompt = """
Gather information to solve the problem. Use "finish" when you feel like you have sufficient information.
"""

files_to_change_abstract_prompt = """Write an abstract minimum plan to address this issue in the least amount of change possible. Try to originate the root causes of this issue. Be clear and concise. 1 paragraph."""

files_to_change_prompt = """
Think step-by-step to break down the requested problem or feature, and then figure out what to change in the current codebase.
Then, provide a list of files you would like to modify, abiding by the following:
* Including the FULL path, e.g. src/main.py and not just main.py, using the repo_tree as the source of truth.
* Prefer modifying existing files over creating new files
* Only modify or create files that definitely need to be touched
* Use detailed, natural language instructions on what to modify, with reference to variable names
* Be concrete with instructions and do not write "check for x" or "look for y". Simply write "add x" or "change y to z".
* There MUST be both create_file and modify_file XML tags
* The list of files to create or modify may be empty, but you MUST leave the XML tags with a single list element with "* None"
* Create/modify up to 5 FILES
* Do not modify non-text files such as images, svgs, binary, etc

You MUST follow the following format delimited with XML tags:

Step-by-step thoughts with explanations: 
* Thought 1 - Explanation 1
* Thought 2 - Explanation 2
...

<modify_file>
* filename_1: instructions_1
* filename_2: instructions_2
...
</modify_file>

<create_file>
* filename_3: instructions_3
* filename_4: instructions_4
...
</create_file>
"""

reply_prompt = """
Write a 1-paragraph response to this user:
* Tell them you have started working on this PR and a rough summary of your plan. 
* Do not start with "Here is a draft", just write the response.
* Use github markdown to format the response.
"""

create_file_prompt = """
You are creating a PR for creating the single new file.

Think step-by-step regarding the instructions and what should be added to the new file.
Next, identify the language and stack used in the repo, based on other files (e.g. React, Typescript, Jest etc.).
Then, create a plan of parts of the code to create, with low-level, detailed references to functions, variables, and imports to create, and what each function does.
Last, create the following file using the following instructions:

DO NOT write "pass" or "Rest of code". Do not literally write "{{new_file}}". You must use the new_file XML tags, and all text inside these tags will be placed in the newly created file.

Reply in the following format:
Commit planning:
file_name = "{filename}"
instructions = "{instructions}"

Step-by-step thoughts with explanations: 
* Thought 1 - Explanation 1
* Thought 2 - Explanation 2
...

Detailed plan of additions:
* Addition 1
* Addition 2
...

commit_message = "{commit_message}"

<new_file>
{{complete_new_file_contents}}
</new_file>
"""

"""
Reply in the format below. 
* You MUST use the new_file XML tags
* DO NOT write ``` anywhere, unless it's markdown
* DO NOT write "pass" or "Rest of code"
* Do not literally write "{{new_file}}".
* Format:
"""

modify_file_plan_prompt = """
Think step-by-step regarding the instructions and how that can be applied to the current file to improve the current codebase.
Then create a plan of parts of the code to modify with detailed references to functions to modify.

File Name: {filename}
<old_file>
{code}
</old_file>

Your instructions to modify the file are: "{instructions}". Limit your changes to the instructions.

Step-by-step thoughts with explanations: 
* Thought 1 - Explanation 1
* Thought 2 - Explanation 2
...

Detailed plan of modifications:
* Modification 1
* Modification 2
...

Lines to change in the file:
* lines a-b
...

Only include the line numbers."""

chunking_prompt = """
We are handling this file in chunks. You have been provided a section of the code.
Any lines that you do not see will be handled, so trust that the imports are managed and any other issues are taken care of.
If you see code that should be modified, please modify it. The changes may not need to be in this chunk, in that case just copy and return the code as is.
"""

modify_file_hallucination_prompt = [{'content': """File Name: (non-existent example)
<old_file>
example = True
if example:
    x = 1 # comment
    print("hello")
    x = 2

def example():
    a = 3
    
</old_file>

Modify this file using GitHub diff patch format.""", 'role': 'user', 'key': 'modify_file_hallucination'},
{'content': """Code Planning:
<code_planning>
Step-by-step thoughts with explanations:
* Thought 1 - This script is an example script not in the repo. To show that I fully understand git diff format, I must write the diffs.

Detailed plan of modifications:
* Modification 1 - Change the output of the print statement from "hello" to "goodbye" as an example modification.
* Modification 2 - I will update the value of a from 3 to 4.

Lines to change in the file:
* lines 4: update print statement
* lines 8: update value of a
</code_planning>

Code Generation:
```
<<<< ORIGINAL
    x = 1 # comment
    print("hello")
    x = 2
====
    x = 1 # comment
    print("goodbye")
    x = 2
>>>> UPDATED

<<<< ORIGINAL
def example():
    a = 3
    
====
def example():
    a = 4
    
>>>> UPDATED
```""", 'role': 'assistant', 'key': 'modify_file_hallucination'}]

# TODO: IMPORTANT: THIS DEPENDS ON THE ABOVE PROMPT, modify_file_hallucination_prompt
modify_file_prompt_3 = """
File Name: {filename}
<old_file>
{code}
</old_file>

---

Code Planning:
<code_planning>
Step-by-step thoughts with explanations: 
* Thought 1 - Explanation 1
* Thought 2 - Explanation 2
...

Detailed plan of modifications:
* Modification 1
* Modification 2
...

Lines to change in the file: (include multiple small changes as opposed to one large change)
* lines a-b: Do x
* lines c: Change to y
...
</code_planning>

Code Generation:
```
Generate a diff based on the given plan, in the following format (do not include "..." anywhere). Always prefer the least amount of changes possible. Do not remove comments.

<<<< ORIGINAL
...
====
...
>>>> UPDATED
``` 

Context: "{instructions}". Limit your changes to the context.
Instructions:
1. Complete the Code Planning step
2. Complete the Code Generation step
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
Your name is Sweep bot. You are an engineer assigned to helping summarize code instructions and code changes.
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

slack_system_message_prompt = "Your name is Sweep bot. You are an engineer assigned to assisting the following Slack user. You will be helpful and friendly, but informal and concise: get to the point. You will use Slack-style markdown when needed to structure your responses."

slack_slash_command_prompt = """
Relevant snippets provided by search engine (decreasing relevance):
<relevant_snippets_in_repo>
{relevant_snippets}
</relevant_snippets_in_repo>

<relevant_paths_in_repo>
{relevant_directories}
</relevant_paths_in_repo>

Repo: {repo_name}: {repo_description}
Username: {username}
Query: {query}

Gather information (i.e. fetch more snippets) to solve the problem. Use "create_pr" if the user asks for changes or you think code changes are needed.
"""

code_repair_check_system_prompt = """\
You are a genius trained for validating code.
You will be given two pieces of code marked by xml tags. The code inside <diff></diff> is the changes applied to create user_code, and the code inside <user_code></user_code> is the final product. 
Our goal is to validate if the final code is valid. This means there's undefined variables, no syntax errors, and the code runs.
"""

code_repair_check_prompt = """\
This is the diff that was applied to create user_code. Only make changes to code in user_code if the code was affected by the diff.
<diff>
{diff}
</diff>

This is the user_code.
<user_code>
{user_code}
</user_code>

Reply in the following format:

Step-by-step thoughts with explanations:
1. No syntax errors: True/False
2. No undefined variables: True/False
3. Code runs: True/False

<valid>True</valid> or <valid>False</valid>
"""

code_repair_system_prompt = """\
You are a genius trained for code stitching.
You will be given two pieces of code marked by xml tags. The code inside <diff></diff> is the changes applied to create user_code, and the code inside <user_code></user_code> is the final product. The intention was to implement a change described as {feature}. 
Our goal is to return a working version of user_code that follows {feature}. We should follow the instructions and make as few edits as possible.
"""
code_repair_prompt = """\
This is the diff that was applied to create user_code. Only make changes to code in user_code if the code was affected by the diff.
<diff>
{diff}
</diff>

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

gradio_system_message_prompt = """Your name is Sweep bot. You are a brilliant and thorough engineer assigned to assist the following user with their problems in the Github repo. You will be helpful and friendly, but informal and concise: get to the point. When you write code to solve tickets, the code works on the first try and is formatted perfectly. You have the utmost care for the user that you write for, so you do not make mistakes. If the user asks you to create a PR, you will use the create_pr function.

Relevant snippets provided by search engine (decreasing relevance):
{snippets}
Repo: {repo_name}
Description: {repo_description}
"""

gradio_user_prompt = """
Respond in the following format (one line per file change, no prefixes, each file should be unique, only files that should be created or changed should go into the plan). There must be a blank line between the summary and the plan:

Response:
Provide a summary of the proposed changes or inquiries for the user. This section will be displayed directly to the user.

Plan:
* filename_1: instructions_1
* filename_2: instructions_2
...
"""

gha_extraction_system_prompt = """\
Your job is to extract the relevant lines from the Github Actions workflow logs for debugging.
"""

# gha_extraction_prompt = """\
# Here are the logs:
# {gha_logs}
# Copy the important lines from the github action logs. Describe the issue as you would report a bug to a developer and do not mention the github action or preparation steps. Only mention the actual issue.
# For example, if the issue was because of github action -> pip install -> python black formatter -> file xyz is broken, only report that file xyz is broken and fails formatting. Do not mention the github action or pip install.
# Make sure to mention the file name and line number of the issue (if applicable).
# Then, suggest 1-2 potential solutions to the issue. Feel free to add ignore comments to the code if you think the linter or static checker has made a mistake.
# """

gha_extraction_prompt = """\
Here are the logs:
{gha_logs}

Copy the lines from the logs corresponding to the error and wrap it in ```. Mention the command that failed.
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

slow_mode_system_prompt = """Your name is Sweep bot. You are a brilliant and meticulous software architect. Your job is to take in the user's GitHub issue and the relevant context from their repository to:
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