
system_prompt = """You are a careful and smart tech lead that wants to avoid production issues. You will be analyzing a set of diffs representing a pull request made to a piece of source code. 
You will also be given the pull request title and description which you will use to determine the intentions of the pull request. Be very concise."""

system_prompt_review = """You are a busy tech manager who is responsible for reviewing prs and identifying any possible production issues. 
You will be analyzing a list of potential issues that have been identified by a previous engineer and determing which issues are severe enough to bring up to the original engineer."""

system_prompt_special_rules = """You are a careful and smart tech lead that wants to avoid production issues. You will be analyzing a set of diffs representing a pull request made to a piece of source code. 
You will also be given the pull request title and description which you will use to determine the intentions of the pull request. Finally you will be given a set of rules to check the pull request changes against.
It is your job to make sure that the pull request changes do not violate any of the given rules.
"""

system_prompt_edge_case_question_creation = """You are a careful and smart tech lead that wants to avoid production issues. You will be analyzing a set of diffs representing a pull request made to a piece of source code.
It is your job to ask a series of detailed and exhaustive set of questions which will then be passed on to the original engineer. The point of this is to make sure that after all the questions have been answered, it will be clear whether or not there are any production issues with the pull request. You are to tailor the questions you create to the code changes provided.
"""

system_prompt_edge_case_answer = """You are a careful and smart tech lead that wants to avoid production issues. You will be analyzing a set of diffs representing a pull request made to a piece of source code.
It is your job to answer a series of questions presented to you by a previous engineer. The questions are meant to help identify any potential production issues with the pull request. You are to answer these questions and using those answers determine if there are any production issues with the pull request.
"""

system_prompt_identify_new_functions = """You are an expert programmer with a keen eye for detail, assigned to analyze a series of code patches in a pull request. Your primary responsibility is to meticulously identify all newly created functions within the code."""

system_prompt_identify_repeats = """You are a proficient programmer tasked with identifying useless utility functions in a codebase. Your job is to identify any useless function definitions.
You will be given a function definition that was just added to the codebase and your job will be to check whether or not this function was actually necessary or not given a series of related code snippets.
"""

system_prompt_pr_summary = """You are a talented software engineer that excels at summarising pull requests for readability and brevity. You will be analysing a series of patches that represent all the changes made in a specific pull request.
It is your job to write a short and concise but still descriptive summary that describes what the pull request accomplishes."""

system_prompt_sort_issues = """You are a helpful and detail-oriented software engineer who is responsible for sorting a list of identified issues based on their severity and importance. 
You will be analyzing a list of issues that have been identified by a previous engineer and determing the severity of each issue.
You will then rank the issues from most severe to least severe based on your analysis."""

user_prompt = """\
# Pull Request Title and Description
Here is the title and description of the pull request, use this to determine the intentions of the pull request:

{pull_request_info}

# Code Review
Here are the changes in the pull request changes given in diff format:
<changes>
{diff}
</changes>

# Instructions
1. Analyze the code changes. Keep in mind what the intentions of the pull request are.
    1a. Review each change individually, examining the code changes line-by-line.
    1b. For each line of code changed, consider:
        - What is the purpose of this line of code?
        - How does this line of code interact with or impact the rest of the files in the pull request?
        - Is this line of code functionally correct? Could it introduce any bugs or errors?
        - Is this line of code necessary? Or could it be an accidental change or commented out code?
    1c. Describe all changes that were made in the diffs. Respond in the following format. (1 paragraph)
<thoughts>
<thinking>
{{Analysis of change 1, include all questions and answers}}
</thinking>
...
</thoughts>
    1d. Provide a final summary for the changes that should be a single sentence and formatted within a <change_summary> tag.
Here is an example, make sure the summary sounds natural and keep it brief and easy to skim over:
<example_change_summary>
Added a new categorization system for snippets in `multi_prep_snippets` and updated the snippet score calculation in `get_pointwise_reranked_snippet_scores`. 
</example_change_summary>
<change_summary>
{{Final summary of the major changes}}
</change_summary>

2. Identify all issues.
    2a. Determine whether there are any functional issues, bugs, edge cases, or error conditions that the code changes introduce or fail to properly handle. Consider the line-by-line analysis from step 1b. (1 paragraph)
    2b. Identify any other potential issues that the code changes may introduce that were not captured by 2a. This could include accidental changes such as commented out code. (1 paragraph)
    2c. Only include issues that you are very confident will cause serious issues that prevent the pull request from being merged. For example, focus only on functional code changes and ignore changes to strings and comments that are purely descriptive.
    2d. Do not make assumptions about existing functions or code. Assume all existing code and system configurations are correct and functioning as intended.
    2e. Do not raise issues over functions being called without error handling. You do not have enough context to determine if the functions are being called correctly.
    2f. You must take into account the intentions of the pull request when identifying issues. Are the the code changes in line with the intentions of the pull request? If the answer is yes then this is not an issue.
    2g. Do not raise issues related to system configuration/resources. For example, do not mention anything about potential resource exhaustion.

Answer each of the above questions in step 2 in the following format:
<issue_identification>
{{Include all answers to the question posed in 2a, to 2f. Example: 2a: A potential...}}
</issue_identification>
"""
user_prompt_special_rules_format = """
# Code Review
Here are the changes in the pull request changes given in diff format:
<changes>
{diff}
</changes>

# Rules
Here are list of rules that are specific to this code review:
<rules>
{special_rules}
</rules>

# Instructions
Along with the rules provided, there may be examples given for each rule. These examples are important to consider when analyzing the code changes.
1. Analyze the rules and examples provided.
    For each rule provided, answer the following:
    Rule #n:
        a. Are there any examples relating to this rule? If no, you may stop here. If yes, repeat the example verbatim here.
        b. For each example, examine if the example provided relates to any code change in the pull request. If it does, explain why, if it doesn't explain why.
Output the questions and answers for each rule in step 1 in the following format:
<examples_analysis>
{{Question and answers for each example in the special_rules section.}}
</examples_analysis> 

2. Analyze the code changes.
    For each rule provided, answer the following questions:
    Rule #n:
        a. Are there code changes in violation of the rule? If yes, then this is an issue that should be raised.
        b. Are there any examples for this rule? If yes, then for each example provided explicitly list out the example and check if the rule applies. Remember that the examples are there for a reason!
Output the questions and answers for each rule in step 2 in the following format:
<rules_analysis>
{{Question and answers for each rule in the special_rules section.}}
</rules_analysis>
"""

user_prompt_edge_case_question_creation_format = """
# Code Review
Here are the changes in the pull request changes given in diff format:
<changes>
{diff}
</changes>

# Instructions
1. Summarize the code changes
Review each change individually, examining the code changes line-by-line. Then review all the changes at once in order to get an idea of how each individual change combines together and what the overall effect of the pull request is.

Respond in the format below, this is mandatory:
<thoughts>
{{Provide your thoughts on the code changes above, providing a summary and how each change ties together with the other changes.}}
</thoughts>

2. Create the questions
You will be given following Cases in which you much generate a series of questions. For each case you will be given guidelines on how to create these questions most effectively. You are to tailor the questions you create to the code changes provided. Make sure to explicitly reference variable names and entities related to the questions and even line numbers if necessary. You MUST create the questions in a way such that an affirmative answer "yes" means that there is an issue with the pull request. That means you should phrase you questions in a way such that they are asking if this issue exists or not. ALWAYS begin the question by asking "Yes or No?"
<cases>
<case_1>
Case 1 - Create questions related to concurrency changes. If there are changes related to concurrency in the pull request you are to generate questions related to concurrency changes.  If not, you may skip this part and go to the next Case. The questions you generate should be an exhaustive list of questions meant to help identify issues with the code changes.
<guidelines_for_case_1>
1. Create questions asking if the variables are mutated unintentionally in any way.
2. When there are variables such as arrays where the order of the data matters, ask questions about whether or not the order of these variables are mutated.
3. Be strict with how you ask your questions. Do not use words like "potentially" or "possibly". If you are asking if an issue exists, ask in a direct manner. Example: Instead of asking "Is there any chance that there is a deadlock" instead ask "Is there a deadlock".
4. Phrase the questions to make sure that if the answer is "Yes" then that means there is an issue with the pull request. Basically you are asking if an issue exists or not.
</guidelines_for_case_1>
</case_1>
</cases>

Respond with ALL your created questions for every case in the following format below, this is mandatory:
<created_questions>
1. Yes or No? Question 1 goes here...
2. Yes or No? Question 2 goes here...
...
n. Yes or No? Question n goes here...
</created_questions>
"""

user_prompt_edge_case_question_answer_format = """
# Code Review
Here are the changes in the pull request changes given in diff format:
<changes>
{diff}
</changes>

# Questions to Answer
<questions_to_answer>
{questions}
</questions_to_answer>

# Instructions
1. Summarize the code changes
Review each change individually, examining the code changes line-by-line. Then review all the changes at once in order to get an idea of how each individual change combines together and what the overall effect of the pull request is.

Respond in the format below, this is mandatory:
<thoughts>
{{Provide your thoughts on the code changes above, providing a summary and how each change ties together with the other changes.}}
</thoughts>

2. Answer the # Questions to Answer
Now you must answer each question, justifying each answer as you go and giving an example from the code changes to support your answer.
First repeat the question verbatim then answer the question in the following format below, this is mandatory:
<questions_and_answers>
1. Question 1 repeated verbatim. Answer: Question 1 answer goes here...
2. Question 2 repeated verbatim. Answer: Question 2 answer goes here...
...
n. Question n repeated verbatim. Answer: Question n answer goes here...
</questions_and_answers>

3. Identify Issues
Based on your answers to the questions above you are now to identify any potential issues that the code changes may introduce. 
Read through each question and answer pair and determine if an issue needs to be raised. 
If there was not enough information to answer a question IT IS NOT AN ISSUE! DO NOT INCLUDE IT AS AN ISSUE AND MOVE ON TO THE NEXT QUESTION. 
"""

user_prompt_issue_output_format = """
[FORMAT]
Finally, format the found issues and root causes using the following XML tags. Each issue description should be a single sentence. 
Include a corresponding line number for the issue. The issue will be raised as a github comment on that exact line in the code file. DO NOT reference the patch or patch number in the description. Format these fields in an <issue> tag in the following manner:

<issues>
<issue>
<issue_description>
{{Issue 1 description, be sure to reference the line/lines of code. Max 1 sentence.}}
</issue_description>
<file_name>
{{Corresponding file name that this issue is in}}
</file_name>
<line_number>
{{Corresponding line number for Issue 1. This is the line the github comment will be on when the issue is raised.}}
</line_number>
</issue>
...
</issues>
If there are no issues found do not include the corresponding <issue> tag.

Focus your analysis solely on potential functional issues with the code changes. Do not comment on stylistic, formatting, or other more subjective aspects of the code."""

user_prompt_review_questions = """
Below are a series of identified issues for the following files {file_names} formatted in the following way:
<potential_issues>
<issue>
<issue_description>
{{Issue 1 description}}
</issue_description>
<file_name>
{{Corresponding file name for Issue 1}}
</file_name>
<line_number>
{{Corresponding line number for Issue 1}}
</line_number>
</issue>
...
</potential_issues>

# Potential Issues

{potential_issues}

Below are the changes made in the pull request as context
# Relevant code files with line numbers

{pr_changes}

Below is the title and description of the pull request. Use this information to determine the intentions of the pull request and then further scrutinize the potential issues.
# Pull Request Title and Description

{pull_request_info}

Below are the comments left on the pull request, possibly from a previous review you did. Use these comments to determine if there are any issues that have already been identified or if there is anything you need to pay attention to.
The issues that have already been identified should not be raised again.
# Previous Review and Comments left on the Pull Request

{comment_threads}

# Instructions
1. Analyze each identified potential issue for the file(s) {file_names}
Review each identified issue individually, formulate 3 questions to answer in order to determine the severity of the issue.
    1a. First formulated question and answer. In order to accomplish this examine the referenced lines of code in the provided code files above.
    1b. Second formulated question and answer. In order to accomplish this examine the referenced lines of code in the provided code files above.
    1c. Third formulated question and answer. In order to accomplish this examine the referenced lines of code in the provided code files above.
    1d. Is this reported issue accurate (double check that the previous reviewer was not mistaken, YOU MUST include the corresponding patch for proof). If the answer to this question is no, then the issue is not severe. 
    1e. Is there accidentally removed or commented out lines of code that has functional utility. In this case double check if this change was intentional or accidental.
    1f. Take into account the intentions of the pull request when identifying issues. Are the code changes in line with the intentions of the pull request? If the answer is yes then this is not an issue.
    1g. Is this issue related to potential security vulnerabilities? If yes, then this issue is NOT severe and should not be included.
    1h. Does this issue have the potential to cause a production crash or introduce a logical error? If yes, then this issue is severe and should be included in the final list of issues.
    1i. Finally was this issue already raised in a comment thread? If yes, then this issue has already been identified and you should not raise it again. You must also provide proof by referencing the exact comment where this issue was raised.
    1j. Is this issue severe enough based on the questions and answers above to prevent the pull request from being merged? Any issue that will cause production to crash or introduce a logical error is considered severe.
"""
user_prompt_review_special_rules = """
In addition to all the above questions you must answer in step 1, the following rules also apply to this file as defined by the user themselves:

<special_rules>
{special_rules}
</special_rules>

For each rule defined in the special_rules section, ask if the issue is in violation of the rule. 
You may be given relevant context for a rule in which case extra attention is required to make sure that the change in the pull request does not violate the rule.
If the issue is in violation of the rule, then it is severe and should be included in the final list of issues.
"""

user_prompt_review_analysis_format = """    
Deliver your analysis including all questions and answers in the following format:
<thoughts>
<thinking>
{{Analysis of the issue, include ALL the questions and answers.
Answer in this format: 
1a. Answer for question 1a...
1b. ...
...
1j. Answer for question 1j...}}
</thinking>
...
</thoughts>"""

user_prompt_review_decisions = """
2. Decide which issues to keep
    2a. Based on your analysis in step 1, now decide which issues to keep and drop. Only include severe issues. To determine if an issue is severe examine the questions and answers you provided above.
    2b. After choosing to keep an issue you are to respond in the following format:
<severe_issues>
<issue>
<issue_description>
{{Issue 1 description}}
</issue_description>
<file_name>
{{Corresponding file name for Issue 1}}
</file_name>
<line_number>
{{Corresponding line number for Issue 1}}
</line_number>
</issue>
...
</severe_issues>
"""

user_prompt_identify_new_functions = """Below are all the patches made to the file {file_name} in this pull request. Use these patches to determine if there are any newly created utility functions.
# PR Patches

{patches}

Below is the file {file_name} with all the above patches applied along with the line numbers. Use this to identify the correct starting and ending line numbers.
# Relevant code file with line numbers

{numbered_code_file}

# Instructions
1. Analyze each of the patches above and identify any newly created utility functions. To determine if a function is newly created, answer the following:
    1a. Note that if a function is renamed such as having of its parameters changed, or if a function has been reworked meaning the contents of the file has changed, this should not be included as a newly created function.
    1b. Is the function created from scratch? If not, the function is not newly created.
    1c. Is there a corresponding patch that shows the creation of the function? If the answer is no, then the function is not newly created. If the answer is yes, give the patch number as proof.
    1d. Is this function a utility function? It should be relatively short and simple, and should not be a class method. If it is too long and complex then do not include it in the final list.
    1e. Answer these questions in the following xml format:
<thinking>
{{Questions and answer for each function that you believe is newly created.}}
</thinking>
2. Based on the questions and answers above return the list of all newly created utility functions in the following xml format:
<newly_created_functions>
<function>
<function_code>
{{Function code copied verbatim for the patch}}
</function_code>
<start_line>
{{Corresponding starting line number for function 1 (inclusive)}}
</start_line>
<end_line>
{{Corresponding ending line number for function 1 (inclusive)}}
</end_line>
</function>
...
</newly_created_functions>
"""

user_prompt_identify_repeats = """
Below is the pull request title and description. Use this to determine the intention of the pull request to help determine if the new function is useless or not.
# Pull Request Title and Description

{pull_request_info}

Below is the function definition that was just added to the code base.
# New Function

{function}

Below are a series of code snippets retrieved from the codebase via vector search. Analyze these code snippets to see if there are any functions that fulfill the exact same purpose and has the same input and output which would render the new function useless.
# Relevant code snippets

{formatted_code_snippets}

Below are the comments left on the pull request, possibly from a previous review you did. Use these comments to determine if there are any issues that have already been identified or if there is anything you need to pay attention to.
The issues that have already been identified should not be raised again.
# Previous Review and Comments left on the Pull Request

{comment_threads}

# Instructions
1. Analyze each of the code snippets above and determine whether or not the new function is useless. Specifically, compare the new function with the existing methods in the code snippets by answering ALL the following questions:
   1a. Purpose: What is the primary purpose of the new function? Is this purpose already served by an existing method? If its purpose is not perfectly serve by an existing method then this function is not useless. If it takes more than one existing function to replicate the functionality of this new function, than this new funciton is not useless.
   1b. Intention: What was the intention behind adding this new function? Is this function meant to be a wrapper or an interface function? If the answer is yes, then this new function is important and should not be removed.
   1c. Functionality: What specific tasks or operations does the new function perform? Are these tasks or operations already handled by existing methods?
   1d. Initialization: What data structures or variables are initialized in the new function? Are similar initializations present in existing methods?
   1e. Data Processing: How does the new function process data (e.g., formatting, extracting, or transforming data)? Are these data processing steps already implemented in existing methods?
   1f. Unique Contributions: Does the new function provide any unique contributions or improvements that are not covered by existing methods? If it does then it should be considered as not useless and should be kept.
   1g. Impact of Removal: Would removing this function require a significant refactor of existing functions? Would the use cases of the existing functions change at all? If the answer is yes to any of these questions the new function is not useless.
   1h. Already Mentioned: Has this issue been previously raised in a comment thread? If yes, then this function is considered not useless. Provide proof of it being raised by referencing the exact comment where this issue was raised.

2. Return your answer in the following xml format:
<useless_new_function>
<thinking>
{{Any thoughts/analysis you have should go here. This is where you MUST answer each of the questions above.}}
</thinking>
<answer>
{{'true' if the new function is useless, 'false' if the new function provides unique contributions.}}
</answer>
<justification>
{{A very brief justification of the decision made. When justifying why make sure to reference relevant functions. Max 1-2 sentences.}}
</justification>
</useless_new_function>"""

user_prompt_pr_summary = """Below are all the patches associated with this pull request along with each of their file names

# All Pull Request Patches

{all_patches}

1. Summarise the major changes using the following principles:
    1a. Begin with a 2-3 line overall summary of what the main goal of the pull request was.
    1b. Now dive deeper into how the main changes for the pull request were accomplished in order of importance.
    1c. Never provide "useless" summaries. "useless" summaries are the following: informing the user a variable or function was created without explaining how it contributes the the main goal of the pull request.
    1d. Instead summarize how the changes were accomplished like this: function `foo` implements feature bar and this had xyz effect of abc.
    1e. It is okay to not summarize minor changes that do not tie into the main goal of the pull request.
    1f. Avoid using overly complex language. For example: instead of the word 'utilize' instead use the word 'use'. 
    1g. Respond in the following xml format:
<pr_summary>
{{Provide a detailed summary here. Be sure to reference relevant entities and variables to make it very clear what you are referencing. Speak in past tense. 
This summary should be maximum 10 sentences. Make sure the summary is not a wall of text, use an adequate amount of new lines.}}
</pr_summary>

Here are a few example <pr_summary></pr_summary> blocks:
<example_pr_summary>
This pull request added support for bulk actions to the admin dashboard.\n\n
A new `BulkActionDropdown` component in `components/BulkActionDropdown.vue` was created that renders a dropdown menu with options for bulk actions that can be performed on selected items in the admin dashboard.\n
The existing `ItemList` component in `components/ItemList.vue` was updated to include checkboxes for each item and to enable the `BulkActionDropdown` when one or more items are selected. \n
A new `bulkDelete` action was added to the item store in `store/item.js` which accepts an array of item IDs and deletes them from the database in a single query. The `BulkActionDropdown` component dispatches this action when the "Delete Selected" option is chosen.\n
Unit tests were added for the `BulkActionDropdown` component and the `bulkDelete` store action in the `components/BulkActionDropdown.test.js` and `store/item.test.js` files respectively.
</example_pr_summary>
<example_pr_summary>
This pull request adds two factor authentication to the user authentication process.\n\n
The `loginUser` function in `handlers/auth.js` now calls the new `verifyTwoFactorCode` function located in `utils/auth-utils.js` after validating the user's password. `verifyTwoFactorCode` is responsible for verifying the user's two-factor authentication code.
\nUnit tests were added for `verifyTwoFactorCode` in `tests/auth.test.js`. These tests covered the following scenarios: providing a valid code, an expired code, and an invalid code.
\nAdditionally, the documentation in `README.md` was updated to reflect the changes to the authentication flow and now describe the new two-factor authentication step.
</example_pr_summary>
"""

user_prompt_sort_issues = """Below are all the identified issues for the pull request. You will be sorting these issues based on severity and importance.

# Identified Issues

{all_issues}

# Instructions
1. Review each issue and determine the severity of the issue.
    1a. Output your analysis in the following format:
<thinking>
{{Analysis of each issue, include the estimated severity and a reason as to why}}
</thinking>
2. Rank the issues based on severity and importance.
    2a. Based on your analysis in step 1, rank the issues from most severe to least severe.
    2b. You must respond with the the following xml format, returning a list of the issue indices in order of severity:

<sorted_issue_indices_by_severity>
{{Sorted indices go here, example: 1, 3, 4 ,2}}
</sorted_issue_indices_by_severity>
"""


pr_changes_prefix = "The following changes were made in the PR. Each change contains all of the patches that were applied to a file, as well as the source code after the change.\n"

pr_review_change_group_format = """
Below are a series of patches for the following files: {file_names}
# All Patches

<all_patches>
{all_patches}
</all_patches>

# Below are the source code files for the following files {file_names} with the above patches applied

<all_source_code>
{all_source_code}
</all_source_code>
"""

source_code_with_patches_format = """
Here is the source code for file {file_name} after applying all patches:
<source_code file_name="{file_name}">
{file_contents}
</source_code>"""

patches_for_file_format = """
<file_patches file_name="{file_name}">
{file_patches}
</file_patches>
"""

patch_format = """\
<patch file_name="{file_name}" index="{index}">
{diff}
</patch>
<patch_annotation file_name="{file_name}" index="{index}">
{annotation}
</patch_annotation>"""

patch_format_without_annotations = """\
<patch file_name="{file_name}" index="{index}">
{diff}
</patch>"""

comment_thread_format = """
<comment_thread file_name="{file_name}" line_number="{line_number}" is_resolved="{is_resolved}">
{comments}
</comment_thread>
"""

comment_format = """<comment file_name="{file_name}" line_number="{line_number}">
{comment_body}
</comment>"""

comment_thread_is_resolved_format = """
The following comment thread has been RESOLVED!
This means the issue you raised in this comment thread is no longer an issue. Do not raise this issue again.
{comment_thread}
"""