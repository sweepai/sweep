"""
List of common prompts used across the codebase.
"""

# Following two should be fused
system_message_prompt = "You're name is Sweep bot. You are an engineer assigned to the following Github ticket. You will be helpful and friendly, but informal and concise: get to the point. You will use Github-style markdown when needed to structure your responses."

human_message_prompt = """
Repo: {repo_name}: {repo_description}
Issue: {issue_url}
Username: {username}
Title: {title}
Description: {description}

Relevant Directories:
{relevant_directories}

Relevant Related Files:
```
{relevant_files}
```
"""

reply_prompt = """Write a short response to this user. Tell them you have started working on this PR and a rough summary of your plan. End with "Give me a minute!"."""

files_to_change_prompt = """
Provide a list of files you would like to modify or create with brief instructions on what to modify, in one line. The list of files to create or modify may be empty, but you MUST leave the header with a single list element with "* None". There MUST be both a Create and a Modify header. Format:

Thoughts: {thoughts}

Create:
* `{filename_1}`: {instructions_1}
* `{filename_2}`: {instructions_2}

Modify:
* `{filename_3}`: {instructions_3}
* `{filename_4}`: {instructions_4}
"""

create_file_prompt = """
Create the following file using the following instructions:

File Name: {filename}

Instructions: {instructions}

Reply in the following format:

Thoughts: {{thoughts}}
Commit Message: {{commit_message}}
```
{{new_code}}
```
"""

modify_file_prompt = """
Modify the following file using the following instructions:

File Name: {filename}
Old Code:
```
{code}
```

Instructions: {instructions}

Reply in the following format:

Thoughts: {{thoughts}}
Commit Message: {{commit_message}}
```
{{new_code}}
```
"""

pr_code_prompt = ""  # TODO: deprecate this


pull_request_prompt = """
Awesome! Could you also provide a PR message in the following format? Content can be in markdown. Thanks!

Title: {title}
Branch Name: {branch_name}
Content:
```
{content}
```
"""
