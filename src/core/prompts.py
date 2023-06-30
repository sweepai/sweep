"""
List of common prompts used across the codebase.
"""

# Following two should be fused
system_message_prompt = "Your name is Sweep bot. You are a brilliant and thorough engineer assigned to the following Github ticket. You will be helpful and friendly, but informal and concise: get to the point. When you write code to solve tickets, the code works on the first try and is formatted perfectly. You have the utmost care for the user that you write for, so you do not make mistakes."
system_message_issue_comment_prompt = "Your name is Sweep bot. You are a brilliant and thorough engineer assigned to the following Github ticket, and a user has just responded with feedback. You will be helpful and friendly, but informal and concise: get to the point. When you write code to solve tickets, the code works on the first try and is formatted perfectly. You have the utmost care for the user that you write for, so you do not make mistakes."

human_message_prompt = """
<relevant_snippets_in_repo>
{relevant_snippets}
</relevant_snippets_in_repo>

<relevant_paths_in_repo>
{relevant_directories}
</relevant_paths_in_repo>

<repo_tree>
{tree}
</repo_tree>

Repo: {repo_name}: {repo_description}
Issue Url: {issue_url}
Username: {username}
Issue Title: {title}
Issue Description: {description}
"""

human_message_review_prompt = """
<relevant_snippets_in_repo>
{relevant_snippets}
</relevant_snippets_in_repo>

<relevant_paths_in_repo>
{relevant_directories}
</relevant_paths_in_repo>

<repo_tree>
{tree}
</repo_tree>

These are the file changes.
We have the file_path, the previous_file_content, the new_file_content, and the diffs.
The file_path is the name of the file.
The previous_file_content is the content of the file before the changes.
The new_file_content is the content of the file after the changes.
The diffs are the lines changed in the file. <added_lines> indicates those lines were added, <deleted_lines> indicates they were deleted.
Keep in mind that we may see a diff for a deletion and replacement, so don't point those out as issues.
{diffs}
"""

diff_section_prompt = """
<file_path>
{diff_file_path}
</file_path>

<previous_file_content>
{previous_file_content}
</previous_file_content>

<new_file_content>
{new_file_content}
</new_file_content>

<file_diffs>
{diffs}
</file_diffs>
"""

review_prompt = """\
I need you to carefully review the code diffs in this pull request. 
The code was written by an inexperienced programmer and may contain accidental deletions, logic errors or other issues.
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
human_message_prompt_comment = """
<relevant_snippets_in_repo>
{relevant_snippets}
</relevant_snippets_in_repo>

<relevant_paths_in_repo>
{relevant_directories}
</relevant_paths_in_repo>

<repo_tree>
{tree}
</repo_tree>

Repo: {repo_name}: {repo_description}
Issue Url: {issue_url}
Username: {username}
Pull Request Title: {title}
Pull Request Description: {description}

These are the file changes.
We have the file_path, the previous_file_content, the new_file_content, and the diffs.
The file_path is the name of the file.
The previous_file_content is the content of the file before the changes.
The new_file_content is the content of the file after the changes.
The diffs are the lines changed in the file. <added_lines> indicates those lines were added, <deleted_lines> indicates they were deleted.
Keep in mind that we may see a diff for a deletion and replacement, so don't point those out as issues.
{diff}
Please handle the user review comment, taking into account the snippets, paths, tree, pull request title, pull request description, and the file changes.
Sometimes the user may not request changes, don't change anything in that case.
User pull request review: {comment}
"""

comment_line_prompt = """\
The user made the review in this file: {pr_file_path}
and on this line: {pr_line}
"""

cot_retrieval_prompt = """
Gather information to solve the problem. Use "finish" when you feel like you have sufficient information.
""" 

files_to_change_prompt = """
Think step-by-step to break down the requested problem or feature, and then figure out what to change in the current codebase.
Then, provide a list of files you would like to modify, abiding by the following:
* Including the FULL path, e.g. src/main.py and not just main.py
* Use a one-line, detailed, natural language instructions on what to modify, with reference to variable names
* The list of files to create or modify may be empty, but you MUST leave the XML tags with a single list element with "* None"
* There MUST be both create and modify XML tags
* Create/modify up to 5 FILES
* Do not modify non-text files, like images, svgs, binary, etc
* You MUST follow the following format:

Step-by-step thoughts with explanations: 
* Thought 1 - Explanation 1
* Thought 2 - Explanation 2
...

<create>
* filename_1: instructions_1
* filename_2: instructions_2
...
</create>

<modify>
* filename_3: instructions_3
* filename_4: instructions_4
...
</modify>
"""

reply_prompt = """
Write a response to this user:
* Ping the user.
* Tell them you have started working on this PR and a rough summary of your plan. 
* Do not start with "Here is a draft", just write the response.
* End with "Give me a minute!".
* Use github markdown to format the response.
"""

create_file_prompt = """
Think step-by-step regarding the instructions and what should be added to the new file.
Then create a plan of parts of the code to create, with low-level, detailed references to functions and variable to create, and what each function does.
Then create the following file using the following instructions:

File Name: {filename}

Instructions: {instructions}

Reply in the following format. DO NOT write "pass" or "Rest of code". Do not literally write "{{new_file}}". You must use the new_file XML tags, and all text inside these tags will be placed in the newly created file.

Step-by-step thoughts with explanations: 
* Thought 1 - Explanation 1
* Thought 2 - Explanation 2
...
Detailed plan of additions:
* Addition 1
* Addition 2
...
Commit Message: {{commit_message}}
<new_file>
{{new_file}}
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

Your instructions to modify the file are: "{instructions}".

Step-by-step thoughts with explanations: 
* Thought 1 - Explanation 1
* Thought 2 - Explanation 2
...
Detailed plan of modifications:
* Modification 1
* Modification 2
...
"""

modify_file_prompt = """
Generate a new_file based on the given plan, ensuring that you:
1. Do not write "pass" statements.
2. Provide complete functions with actual business logic. It is imperative that we do not leave any work to the user/future readers of this code.
3. Do not write new "todo" comments.
4. Do not write incomplete functions or line numbers.
5. Make sure code follows programming language conventions in repo

Instead of writing "# Rest of Code", specify the lines to copy from the old file using an XML tag, inclusive (e.g., "<copied>0-25</copied>"). Make sure to use this exact format.
Copy the correct line numbers and copy as long of a prefix and suffix as possible. For instance, if you want to insert code after line 50, start with "<copied>0-50</copied>".
Example: If you want to insert code after lines 50 and 75:
<new_file>
<copied>0-50</copied>
def main():
     print("hello world")
<copied>51-100</copied>
</new_file>
"""

pr_code_prompt = ""  # TODO: deprecate this


pull_request_prompt = """
Awesome! Could you also provide a PR message in the following format? Content should be in Github style markdown. Thanks!

Title: {title}
Branch Name: {branch_name}
<content>
{content}
</content>
"""

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

code_repair_system_prompt = """\
You are a genius trained for code repair. 
You will be given two pieces of code marked by xml tags. The code inside <diff></diff> is the difference betwen the user_code and the original code, and the code inside <user_code></user_code> is a user's attempt at adding a change described as {feature}. 
Our goal is to return a working version of user_code that follows {feature}.

Instructions:
* Keep the logic changes from user_code.
* Fix any issues using our knowledge of both the diff and user_code files. 
* Fix syntax errors and accidentally deleted lines.
* Do not perform code style cleanup.
* Do not add or remove any whitespace besides what is necessary to fix syntax errors.
* Do not add or remove any comments.
"""

code_repair_prompt = """\
<diff>
{diff}
</diff>
<user_code>
{user_code}
</user_code>
This is the user_code. 
Return the repaired user_code without xml tags. All of the text you return will be placed in the file. Revert any unrelated deletions to user_code, using the diff and described change.
"""
