"""
Take a PR and provide an AI generated review of the PR.
"""
import copy
import multiprocessing
import os
import re

import git
import numpy as np
from sklearn.cluster import DBSCAN
from tqdm import tqdm
from sweepai.chat.api import posthog_trace
from sweepai.config.client import SweepConfig
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, UnsuitableFileException
from sweepai.core.review_annotations import get_diff_annotations
from sweepai.core.sweep_bot import safe_decode
from sweepai.core.vector_db import cosine_similarity, embed_text_array
from sweepai.dataclasses.codereview import CodeReview, CodeReviewByGroup, CodeReviewIssue, FunctionDef, GroupedFilesForReview, PRChange, Patch
from sweepai.logn.cache import file_cache
from sweepai.utils.event_logger import logger, posthog
from sweepai.utils.chat_logger import ChatLogger
from github.Repository import Repository
from github.PullRequest import PullRequest

from sweepai.utils.file_utils import read_file_with_fallback_encodings
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo, update_file
from sweepai.utils.hash import hash_sha256
from sweepai.utils.str_utils import add_line_numbers, extract_object_fields_from_string, extract_objects_from_string, object_to_xml, objects_to_xml, remove_lines_from_text
from sweepai.utils.ticket_rendering_utils import parse_issues_from_code_review
from sweepai.utils.ticket_utils import get_top_k_snippets

# approximately 120k tokens - this is an underestimate which is intentional, even if we can use 128k context we dont want to use all of it
MAX_CHAR_BUDGET = 120000 * 3.5

def get_pr_diffs(repo: Repository, pr: PullRequest):
    base_sha = pr.base.sha
    head_sha = pr.head.sha

    comparison = repo.compare(base_sha, head_sha)
    file_diffs = comparison.files

    pr_diffs = []
    for file in file_diffs:
        diff = file.patch
        if (
            file.status == "added"
            or file.status == "modified"
            or file.status == "removed"
        ):
            pr_diffs.append((file.filename, diff))
        elif file.status == "copied":
            pass
        elif file.status == "renamed":
            pr_diffs.append((file.filename, f"{file.filename} was renamed."))
        else:
            logger.info(
            f"File status {file.status} not recognized"
            )
    return pr_diffs

def validate_diff(file_name: str, diff: str):
    MAX_DIFF_LENGTH = 1000
    if not diff:
        return "diff is empty", False
    if not file_name:
        return "file name is empty", False
    if len(diff.split("\n")) > MAX_DIFF_LENGTH:
        return f"diff is over {MAX_DIFF_LENGTH}", False
    return "", True

@file_cache()
def get_pr_changes(repo: Repository, pr: PullRequest) -> tuple[dict[str, PRChange], list[str], list[str]]:
    sweep_config: SweepConfig = SweepConfig()
    base_sha = pr.base.sha
    head_sha = pr.head.sha

    comparison = repo.compare(base_sha, head_sha)
    file_diffs = comparison.files

    pr_diffs = {}
    dropped_files = [] # files that were dropped due them being commonly ignored
    unsuitable_files: list[tuple[str, Exception]] = [] # files dropped for other reasons such as being way to large or not encodable, error objects included
    for file in tqdm(file_diffs, desc="Annotating diffs"):
        file_name = file.filename
        diff = file.patch
        # Ensure diff is a string 
        if not isinstance(diff, str):
            diff = str(diff)
        
        # we can later migrate this to use a cloned repo and fetch off of two hashes  
        reason, is_valid_diff = validate_diff(file_name, diff)
        if not is_valid_diff:
            logger.info(
                f"Skipping invalid diff for file {file_name} because {reason}"
            )
            continue
        previous_filename = file.previous_filename or file.filename

        # drop excluded files: for example package-lock.json files
        if sweep_config.is_file_excluded(file_name):
            dropped_files.append(file_name)
            continue
        
        errored = False
        e = None
        if file.status == "added":
            old_code = ""
        else:
            try:
                old_code = safe_decode(repo=repo, path=previous_filename, ref=base_sha)
                if old_code is None:
                    raise UnsuitableFileException("Could not decode file")
            except Exception as e_:
                e = e_
                errored = True
                unsuitable_files.append((file_name, e))
        if file.status == "removed":
            new_code = ""
        else:
            try:
                new_code = safe_decode(repo=repo, path=file.filename, ref=head_sha)
                if new_code is None:
                    raise UnsuitableFileException("Could not decode file")
            except Exception as e_:
                e = e_
                errored = True
                unsuitable_files.append((file_name, e))

        # drop unsuitable files
        if new_code: 
            suitable, reason = sweep_config.is_file_suitable(new_code)
            if not suitable:
                errored = True
                e = UnsuitableFileException(reason)
                unsuitable_files.append((file_name, e))

        if errored:
            posthog.capture(
                "get_pr_changes", 
                "get_pr_changes error", 
                properties={"error": str(e), "file_name": file_name, "pr": str(pr), "repo": str(repo)}
            )
            continue

        status = file.status
        pr_change = PRChange(
            file_name=file_name,
            diff=diff,
            old_code=old_code,
            new_code=new_code,
            status=status,
            patches=split_diff_into_patches(diff, file_name)
        )
        diff_annotations = get_diff_annotations(
            source_code=pr_change.new_code,
            diffs=[patch.changes for patch in pr_change.patches],
            file_name=pr_change.file_name
        )
        pr_change.annotations = diff_annotations
        pr_diffs[file_name] = pr_change
    return pr_diffs, dropped_files, unsuitable_files

def split_diff_into_patches(diff: str, file_name: str) -> list[Patch]:
    patches = []
    hunks = re.findall(r'@@ -\d+,\d+ \+\d+,\d+ @@.*?(?=\n@@ -|\Z)', diff, re.DOTALL)
    for hunk in hunks:
        line_numbers = re.findall(r'-(\d+),(\d+) \+(\d+),(\d+)', hunk)
        if line_numbers:
            old_start, old_count, new_start, new_count = map(int, line_numbers[0])
            changes = hunk[hunk.index('@@'):].strip()
            patch = Patch(
                file_name=file_name,
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                changes=changes
            )
            patches.append(patch)
    return patches

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


# format only the patches for the PRChange
def format_patches_for_pr_change(pr_change: PRChange, include_patch_annotations: bool = True):
    patches = ""
    for idx, patch in enumerate(pr_change.patches):
        if include_patch_annotations:
            patches += patch_format.format(
                file_name=pr_change.file_name,
                index=idx + 1,
                diff=patch.changes,
                annotation=pr_change.annotations[idx]
            )
        else:
            patches += patch_format_without_annotations.format(
                file_name=pr_change.file_name,
                index=idx + 1,
                diff=patch.changes,
            )
        if idx < len(pr_change.patches) - 1:
            patches += "\n"
    formatted_patches = patches_for_file_format.format(
        file_name=pr_change.file_name,
        file_patches=patches
    )
    return formatted_patches

# prunes a file based on the patches for that file, removes long sections in between
def smart_prune_file_based_on_patches(file_contents: str, patches: list[Patch], context_lines: int = 10):
    if not file_contents:
        return file_contents
    lines = file_contents.splitlines(keepends=True)
    num_of_lines = len(lines)
    patch_ranges = []
    # if we dont have patches we naively truncate the file to around 100 lines
    if len(patches) == 0:
        if len(lines) > 100:
            return "".join(lines[:100]) + "...\n"
        else:
            return file_contents

    # sort patches based on new_start
    sorted_patches = sorted(patches, key=lambda patch: patch.new_start)
    for patch in sorted_patches:
        start = max(0, patch.new_start - context_lines - 1)
        end = min(num_of_lines - 1, patch.new_start + patch.new_count + context_lines - 1)
        if len(patch_ranges) == 0:
            patch_ranges.append((start, end))
        else: 
            previous_range = patch_ranges[-1]
            # combine if overlap
            if previous_range[1] >= start:
                patch_ranges[-1] = (previous_range[0], end)
            else:
                patch_ranges.append((start, end))
    # now replace any sections not within the patch ranges with ...
    new_lines = []
    for i, range in enumerate(patch_ranges):
        range_lines = lines[range[0]: range[1] + 1]
        # with list slicing we can safely extend past the actual length of the array
        if range[0] != 0:
            range_lines = ['...\n'] + range_lines
        # check if we need trailing ...
        if i == len(patch_ranges) - 1 and range[1] < len(lines) - 1:
            range_lines = range_lines + ['...\n']
        new_lines.extend(range_lines)
    new_file_contents = "".join(new_lines)
    return new_file_contents

def format_pr_changes(
    pr_changes: dict[str, PRChange],
    include_annotations: bool = True,
    truncate: bool = False
) -> str:
    formatted_changes = ""
    all_formatted_patches = ""
    all_formatted_source_code = ""
    for file_name, pr_change in pr_changes.items():
        # format patches
        formatted_patches_for_file = format_patches_for_pr_change(
            pr_change, include_patch_annotations=include_annotations
        )
        all_formatted_patches += formatted_patches_for_file
        # format source code
        if truncate:
            formatted_source_code = source_code_with_patches_format.format(
                file_name=file_name, file_contents=smart_prune_file_based_on_patches(
                    add_line_numbers(pr_change.new_code), 
                    pr_change.patches
                )
            )
        else:
            formatted_source_code = source_code_with_patches_format.format(
                file_name=file_name, file_contents=add_line_numbers(pr_change.new_code)
            )
        all_formatted_source_code += formatted_source_code
    file_names = ", ".join(pr_changes.keys())
    formatted_changes = pr_review_change_group_format.format(
        file_names=file_names,
        all_patches=all_formatted_patches,
        all_source_code=all_formatted_source_code
    )
    return formatted_changes, all_formatted_patches, all_formatted_source_code

# render a group of pr changes for review
def render_pr_changes(pr_changes: dict[str, PRChange]) -> str:
    formatted_changes, formatted_patches, formatted_source_code = format_pr_changes(pr_changes)
    if len(formatted_changes) >= MAX_CHAR_BUDGET:
        # go again with pruned code
        formatted_changes, formatted_patches, formatted_source_code = format_pr_changes(pr_changes, truncate=True)
    if len(formatted_changes) >= MAX_CHAR_BUDGET:
        # go again without annotations and prune code
        formatted_changes, formatted_patches, formatted_source_code = format_pr_changes(
            pr_changes, truncate=True, include_annotations=False
        )
    if len(formatted_changes) >= MAX_CHAR_BUDGET:
        # simply too many changes to handle, split them up
        formatted_changes, formatted_patches, formatted_source_code = "", "", ""
    return formatted_changes, formatted_patches, formatted_source_code

# render all changes for all groups, handle cases where grouped files are too large
def format_all_pr_changes_by_groups(
    grouped_files: dict[str, list[str]],
    pr_changes: dict[str, PRChange]
):
    formatted_pr_changes_by_groups: dict[str, GroupedFilesForReview] = {}
    for _, files_to_review in grouped_files.items():
        # get all relevant PRChange objects
        changes_to_review = {file_name: pr_changes[file_name] for file_name in files_to_review}
        # build change overview
        formatted_changes, formatted_patches, formatted_source_code = render_pr_changes(changes_to_review)
        if formatted_changes:
            group = GroupedFilesForReview(
                file_names=files_to_review,
                rendered_changes=formatted_changes,
                rendered_patches=formatted_patches,
                rendered_source_code=formatted_source_code
            )
            formatted_pr_changes_by_groups[group.group_name] = group
        else: # too large break up
            for file_name in files_to_review:
                changes_to_review = {file_name: pr_changes[file_name]}
                formatted_changes, formatted_patches, formatted_source_code = render_pr_changes(changes_to_review)
                group = GroupedFilesForReview(
                    file_names=[file_name],
                    rendered_changes=formatted_changes,
                    rendered_patches=formatted_patches,
                    rendered_source_code=formatted_source_code
                )
                formatted_pr_changes_by_groups[group.group_name] = group
    return formatted_pr_changes_by_groups


system_prompt = """You are a careful and smart tech lead that wants to avoid production issues. You will be analyzing a set of diffs representing a pull request made to a piece of source code. 
You will also be given the pull request title and description which you will use to determine the intentions of the pull request. Be very concise."""

system_prompt_review = """You are a busy tech manager who is responsible for reviewing prs and identifying any possible production issues. 
You will be analyzing a list of potential issues that have been identified by a previous engineer and determing which issues are severe enough to bring up to the original engineer."""

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
    2d. Do not make assumptions about existing functions or code.

Answer each of the above questions in step 2 in the following format:
<issue_identification>
{{Include all answers to the question posed in 2a, 2b, 2c and 2d}}
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
        a. Are there any examples relating to this rule? If no, you may stop here.
        b. If there are examples, for each example, explain how the example relates to the rule and give an example code change that would violate the rule.
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

user_prompt_issue_output_format = """
[FORMAT]
Finally, format the found issues and root causes using the following XML tags. Each issue description should be a single sentence. Include the corresponding start and end line numbers of the change, these line numbers should be at most 50 apart. DO NOT reference the patch or patch number in the description. Format these fields in an <issue> tag in the following manner:

<issues>
<issue>
<issue_description>
{{Issue 1 description}}
</issue_description>
<file_name>
{{Corresponding file name that this issue is in}}
</file_name>
<start_line>
{{Corresponding starting line number for Issue 1}}
</start_line>
<end_line>
{{Corresponding ending line number for Issue 1 (this can be the same as the start_line)}}
</end_line>
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
<start_line>
{{Corresponding starting line number for Issue 1}}
</start_line>
<end_line>
{{Corresponding ending line number for Issue 1 (this can be the same as the start_line)}}
</end_line>
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

# Instructions
1. Analyze each identified potential issue for the file {file_names}
    1a. Review each identified issue individually, formulate 3-5 questions to answer in order to determine the severity of the issue.
    1b. Answer the questions formulated in step 1a. In order to accomplish this examine the referenced lines of code in the provided code files above.
    1c. Answer the following questions in addition to the ones you generated in steps 1a. Is this reported issue accurate (double check that the previous reviewer was not mistaken, YOU MUST include the corresponding patch for proof)? If the answer to this question is no, then the issue is not severe. 
    1d. Determine whether or not this issue is severe enough to prevent the pull request from being merged or not. For example, any potential logical error is considered severe.
    1e. Take note of some common issues: Accidently removing or commenting out lines of code that has functional utility. In this case double check if this change was intentional or accidental.
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
{{Analysis of the issue, include ALL the questions and answers}}
</thinking>
...
</thoughts>"""
user_prompt_review_decisions = """
2. Decide which issues to keep
    2a. Based on your analysis in step 1, now decide which issues to keep and drop. Only include severe issues.
    2b. After choosing to keep an issue you are to respond in the following format:
<severe_issues>
<issue>
<issue_description>
{{Issue 1 description}}
</issue_description>
<file_name>
{{Corresponding file name for Issue 1}}
</file_name>
<start_line>
{{Corresponding starting line number for Issue 1}}
</start_line>
<end_line>
{{Corresponding ending line number for Issue 1}}
</end_line>
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

# Instructions
1. Analyze each of the code snippets above and determine whether or not the new function is useless. Specifically, compare the new function with the existing methods in the code snippets by answering ALL the following questions:
   1a. Purpose: What is the primary purpose of the new function? Is this purpose already served by an existing method? If its purpose is not perfectly serve by an existing method then this function is not useless. If it takes more than one existing function to replicate the functionality of this new function, than this new funciton is not useless.
   1b. Intention: What was the intention behind adding this new function? Is this function meant to be a wrapper or an interface function? If the answer is yes, then this new function is important and should not be removed.
   1c. Functionality: What specific tasks or operations does the new function perform? Are these tasks or operations already handled by existing methods?
   1d. Initialization: What data structures or variables are initialized in the new function? Are similar initializations present in existing methods?
   1e. Data Processing: How does the new function process data (e.g., formatting, extracting, or transforming data)? Are these data processing steps already implemented in existing methods?
   1f. Unique Contributions: Does the new function provide any unique contributions or improvements that are not covered by existing methods? If it does then it should be considered as not useless and should be kept.
   1g. Impact of Removal: Would removing this function require a significant refactor of existing functions? Would the use cases of the existing functions change at all? If the answer is yes to any of these questions the new function is not useless.

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

CLAUDE_MODEL = "claude-3-opus-20240229"

class PRReviewBot(ChatGPT):
    # check if there are special .md rules to see if there are additional rules to check for
    # assumes by default the file name is gpt.md
    def get_special_rules(
        self, 
        cloned_repo: ClonedRepo, 
        file_names: list[str], 
        special_rule_file: str = "SWEEP.md"
    ):
        special_rules = ""
        for file_name in file_names:
            # ensure file exists and this is not a GPT.md file
            full_path = os.path.join(cloned_repo.repo_dir, file_name)
            base_file = os.path.basename(file_name)
            if not os.path.exists(full_path) or base_file == special_rule_file:
                logger.error(f"Failure fetching special rules file for {file_name} as it does not exist.")
                return special_rules
            
            subdirectories = file_name.split(os.path.sep)
            directories_to_check = []
            # Loop from the end to the beginning, excluding the file itself
            for i in range(len(subdirectories) - 1, 0, -1):
                directories_to_check.append(
                    os.path.join(cloned_repo.repo_dir, os.path.join(*subdirectories[:i]))
                )
            # append the base directory
            directories_to_check.append(cloned_repo.repo_dir)
            # now check all directories for the special rule file, we add on to special rules if we find it
            for directory in directories_to_check:
                special_rule_path = os.path.join(directory, special_rule_file)
                if os.path.exists(special_rule_path):
                    special_rules += read_file_with_fallback_encodings(special_rule_path)
        return special_rules
    # get a comprehensive pr summary
    def get_pr_summary(self, formatted_patches: str, chat_logger: ChatLogger = None):
        self.messages = [
            Message(
                role="system",
                content=system_prompt_pr_summary,
            )
        ]
        formatted_user_prompt = user_prompt_pr_summary.format(all_patches=formatted_patches)
        pr_summary_response = self.chat_anthropic(
            content=formatted_user_prompt,
            temperature=0.1,
            model=CLAUDE_MODEL,
            use_openai=True,
        )
        pr_summary = ""
        pr_summary_pattern = r"<pr_summary>(?P<pr_summary>.*?)</pr_summary>"
        pr_summary_match = re.search(pr_summary_pattern, pr_summary_response, re.DOTALL)
        if pr_summary_match:
            pr_summary = pr_summary_match.group("pr_summary")
        if chat_logger:
            chat_logger.add_chat(
                {
                    "model": self.model,
                    "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                    "output": "END OF MESSAGES",
                })
        return pr_summary
    
    # fetch all potential issues for each file based on the diffs of that file
    def review_code_changes_by_file(
        self, 
        pr_changes: dict[str, PRChange],
        formatted_pr_changes_by_group: dict[str, GroupedFilesForReview], 
        cloned_repo: ClonedRepo, 
        pull_request_info: str,
        chat_logger: ChatLogger = None, 
        seed: int | None = None
    ):
        code_reviews_by_group = {}
        # loop through all groups
        for group_name, grouped_files in formatted_pr_changes_by_group.items():
            file_names = grouped_files.file_names
            rendered_changes = grouped_files.rendered_changes
            # get all relevant PRChange objects
            # build prompt
            self.messages = [
                Message(
                    role="system",
                    content=system_prompt,
                )
            ]
            formatted_user_prompt = user_prompt.format(
                diff=rendered_changes, pull_request_info=pull_request_info
            )
            formatted_user_prompt += user_prompt_issue_output_format
            if len(formatted_user_prompt) > MAX_CHAR_BUDGET:
                # if we exceed the budget we need to prune the file
                posthog.capture(
                    "review_code_changes_by_file", 
                    "review_code_changes_by_file budget exceeded", 
                    properties={"file_names": file_names, "body": formatted_user_prompt}
                )
            code_review_response = self.chat_anthropic(
                content=formatted_user_prompt,
                temperature=0,
                model=CLAUDE_MODEL,
                use_openai=True,
                seed=seed
            )
            # make a seperate call for the special rules
            # check if there are special rules we need to follow for this file by seeing if the files "SWEEP.md" exists
            special_rules = self.get_special_rules(cloned_repo, file_names)
            if special_rules:
                formatted_user_prompt_special_rules = user_prompt_special_rules_format.format(diff=rendered_changes, special_rules=special_rules)
                formatted_user_prompt_special_rules += user_prompt_issue_output_format
                special_rules_response = self.chat_anthropic(
                    content=formatted_user_prompt_special_rules,
                    temperature=0,
                    model=CLAUDE_MODEL,
                    seed=seed
                )
                code_review_response += special_rules_response
            diff_summary = ""
            diff_summary_pattern = r"<diff_summary>(.*?)</diff_summary>"
            diff_summary_matches = re.findall(diff_summary_pattern, code_review_response, re.DOTALL)
            if diff_summary_matches:
                # join all of them into a single string
                diff_summary = "\n".join([match.strip() for match in diff_summary_matches])
            issues = ""
            issues_pattern = r"<issues>(.*?)</issues>"
            issues_matches = re.findall(issues_pattern, code_review_response, re.DOTALL)
            if issues_matches:
                issues = "\n".join([match.strip() for match in issues_matches])
            potential_issues = parse_issues_from_code_review(issues)
            code_reviews_by_group[group_name] = CodeReviewByGroup(
                file_names=file_names,
                diff_summary=diff_summary, 
                issues=potential_issues, 
                potential_issues=[]
            )
            if chat_logger:
                chat_logger.add_chat(
                    {
                        "model": self.model,
                        "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                        "output": "END OF MESSAGES",
                    })
        return code_reviews_by_group

    # review the generated issues more critically for each file to see if they are actually important or not
    def review_code_issues_by_file(
        self, 
        pr_changes: dict[str, PRChange], 
        formatted_pr_changes_by_group: dict[str, GroupedFilesForReview], 
        code_reviews_by_group: dict[str, CodeReviewByGroup], 
        cloned_repo: ClonedRepo,
        pull_request_info: str,
        chat_logger: ChatLogger = None,
        seed: int | None = None
    ):
        # go file by file
        for group_name, code_review_by_group in code_reviews_by_group.items():
            file_names = code_review_by_group.file_names
            self.messages = [
                Message(
                    role="system",
                    content=system_prompt_review,
                )
            ]
            # if no issues were identified continue to next file
            if not code_review_by_group.issues:
                continue
            # convert our CodeReviewIssue list to an xml string
            potential_issues_string = objects_to_xml(code_review_by_group.issues, "issue", outer_field_name="potential_issues")
            # now prepend all other pr changes to the current pr change
            all_other_pr_changes = "\n\n".join([file_group.rendered_patches for group, file_group in formatted_pr_changes_by_group.items() if group != group_name])
            # create user prompt
            formatted_user_prompt = user_prompt_review_questions.format(
                file_names=code_review_by_group.get_all_file_names(), 
                potential_issues=potential_issues_string, 
                pull_request_info=pull_request_info,
                pr_changes=f"{all_other_pr_changes}\n\n{formatted_pr_changes_by_group[group_name]}"
            )
            special_rules = self.get_special_rules(cloned_repo, file_names)
            if special_rules:
                formatted_user_prompt += user_prompt_review_special_rules.format(special_rules=special_rules)
            formatted_user_prompt += user_prompt_review_analysis_format
            formatted_user_prompt += user_prompt_review_decisions
            # get response
            code_review_response = self.chat_anthropic(
                content=formatted_user_prompt,
                temperature=0,
                model=CLAUDE_MODEL,
                use_openai=True,
                seed=seed
            )

            severe_issues_pattern = r"<severe_issues>(.*?)</severe_issues>"
            issues_matches = re.findall(severe_issues_pattern, code_review_response, re.DOTALL)
            if issues_matches:
                issues = "\n".join([match.strip() for match in issues_matches])
                potential_issues = parse_issues_from_code_review(issues)
            else:
                potential_issues = []
            
            # update the issues
            code_reviews_by_group[group_name].issues = potential_issues
            
            if chat_logger:
                chat_logger.add_chat(
                    {
                        "model": self.model,
                        "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                        "output": "END OF MESSAGES",
                    })
        return code_reviews_by_group

    # given a list of changes identify newly created functions
    def identify_functions_in_patches(
        self,
        pr_changes: dict[str, PRChange],
        chat_logger: ChatLogger | None = None
    ):
        newly_created_functions: dict[str, list[FunctionDef]] = {}
        files_to_patches: dict[str, str] = {}
        files_to_pr_change: dict[str, PRChange] = {}
        # format all patches for all files
        for file_name, pr_change in pr_changes.items():
            patches = format_patches_for_pr_change(pr_change)
            files_to_patches[file_name] = patches
            files_to_pr_change[file_name] = pr_change
        # go file by file
        for file_name, patches in files_to_patches.items():
            if "SWEEP.md" in file_name: # jank but temporary
                continue
            pr_change = files_to_pr_change[file_name]
            self.messages = [
                Message(
                    role="system",
                    content=system_prompt_identify_new_functions,
                )
            ]
            numbered_code_file = add_line_numbers(files_to_pr_change[file_name].new_code, start=1)
            # only need code related to patches
            numbered_code_file = smart_prune_file_based_on_patches(
                numbered_code_file, 
                files_to_pr_change[file_name].patches,
                context_lines=5
            )

            formatted_user_prompt = user_prompt_identify_new_functions.format(
                file_name=file_name, patches=patches, numbered_code_file=numbered_code_file
            )
            new_functions_response = self.chat_anthropic(
                content=formatted_user_prompt,
                temperature=0,
                model=CLAUDE_MODEL,
                use_openai=True
            )
            if chat_logger:
                chat_logger.add_chat(
                    {
                        "model": self.model,
                        "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                        "output": "END OF MESSAGES",
                    })
            # extract function defs from string
            function_def_params = ["function_code", "start_line", "end_line"]
            newly_created_functions_regex = r'<newly_created_functions>(?P<content>.*?)<\/newly_created_functions>'
            newly_created_functions_match = re.search(newly_created_functions_regex, new_functions_response, re.DOTALL)
            if newly_created_functions_match:
                extracted_functions, _ = extract_objects_from_string(newly_created_functions_match.group("content"), "function", function_def_params)
                patches = pr_change.patches
                for extracted_function in extracted_functions:
                    # do some basic double checking, make sure the start and end lines make sense
                    # the start and end lines should fall within the start and end of one patch, if they dont, then it is clearly wrong
                    try:
                        start = int(extracted_function.get("start_line", -1))
                        end = int(extracted_function.get("end_line", -1))
                    except ValueError as e:  # invalid start and end lines
                        logger.error(
                            "Non fatal error in identify_functions_in_patches attempting to extract start and end lines."
                        )
                        posthog.capture(
                            "identify_repeated_functions",
                            "identify_repeated_functions error line_numbers",
                            properties={
                                "error": str(e),
                                "extracted_function": str(extracted_function),
                            },
                        )
                        start = -1
                        end = -1
                    if start != -1 and end != -1:
                        valid_function = False
                        for patch in patches:
                            if start >= patch.new_start and end <= (patch.new_start + patch.new_count):
                                valid_function = True
                                break
                        if valid_function:
                            if file_name not in newly_created_functions:
                                newly_created_functions[file_name] = []
                            newly_created_functions[file_name].append(FunctionDef(**{**extracted_function, "file_name": file_name}))
                        else:
                            logger.warning(f"Extracted function was dropped due to incorrect start and end lines!\nFunction:\n{extracted_function}")
            else:
                newly_created_functions[file_name] = []
        return newly_created_functions
    
    # identifies any repeated utility function definitons and raises them as codereviewissue
    def identify_repeated_functions(
        self, 
        cloned_repo: ClonedRepo, 
        newly_created_functions_dict: dict[str, list[FunctionDef]],
        pull_request_info: str,
        chat_logger: ChatLogger | None = None
    ) -> dict[str, list[CodeReviewIssue]]:
        repeated_functions_code_issues: dict[str, list[CodeReviewIssue]] = {}
        for file_name, newly_created_functions in newly_created_functions_dict.items():
            if "SWEEP.md" in file_name: # jank but temporary
                continue
            # keep copy of edited files to revert later
            modified_files_dict: dict[str, dict[str, str]] = {}
            modified_files_dict[file_name] = {"original": cloned_repo.get_file_contents(file_name)}
            repeated_functions_code_issues[file_name] = []
            # do a similarity search over the chunked code base to see if the function name matches anything
            for function in newly_created_functions:
                # remove the function definition from the file to prevent biased results
                modified_files_dict[file_name]["modified"] = remove_lines_from_text(
                    modified_files_dict[file_name]["original"], start=int(function.start_line),end=int(function.end_line)
                )
                # now update the cloned repo file in both repo_dir and cached_dir
                try:
                    update_file(cloned_repo.repo_dir, file_name, modified_files_dict[file_name]["modified"])
                    update_file(cloned_repo.cached_dir, file_name, modified_files_dict[file_name]["modified"])
                except Exception as e:
                    logger.error(f"Failure updating file {cloned_repo.repo_dir}{function.file_name}: {e}")
                    posthog.capture(
                        "identify_repeated_functions", 
                        "identify_repeated_functions error updating", 
                        properties={"error": str(e), "cloned_repo.repo_dir": cloned_repo.repo_dir, "file_name": function.file_name}
                    )
                    raise e
                file_hash = hash_sha256(modified_files_dict[file_name]["modified"])
                # get the top five snippets and then pass those into sweep to ask if there are any repeated function definitions
                ranked_snippets, _, _ = get_top_k_snippets(
                    cloned_repo, 
                    function.function_code, 
                    k=3, 
                    include_docs=False, 
                    include_tests=False, 
                    do_not_use_file_cache=True,
                    seed=file_hash
                )
                formatted_code_snippets = "\n\n".join(
                    [f"<code_snippet file_name='{snippet.file_path}' snippet_index='{idx}'>\n{snippet.get_snippet()}\n</code_snippet>" for idx, snippet in enumerate(ranked_snippets)]
                )
                formatted_user_prompt = user_prompt_identify_repeats.format(
                    function=f"<new_function>\n{function.function_code}\n</new_function>", 
                    formatted_code_snippets=formatted_code_snippets,
                    pull_request_info=pull_request_info,
                )
                self.messages = [
                    Message(
                        role="system",
                        content=system_prompt_identify_repeats,
                    )
                ]
                repeated_functions_response = self.chat_anthropic(
                    content=formatted_user_prompt,
                    temperature=0.1,
                    model=CLAUDE_MODEL,
                )
                if chat_logger:
                    chat_logger.add_chat(
                        {
                            "model": self.model,
                            "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                            "output": "END OF MESSAGES",
                        })
                repeated_function_params = ['answer', 'justification']
                repeated_function, _, failed_param = extract_object_fields_from_string(repeated_functions_response, repeated_function_params)
                # if extraction fails
                if failed_param == "answer":
                    logger.error("Failure in extract_object_fields_from_string")
                    posthog.capture(
                        "extract_object_fields_from_string", "extract_object_fields_from_string failed", properties={"text": repeated_functions_response, "params": str(repeated_function_params)}
                    )
                else:
                    # case insensitive match
                    answer_true = r'true'
                    if bool(re.search(answer_true, repeated_function['answer'], re.IGNORECASE)):
                        justification = repeated_function.get("justification", "")
                        new_code_issue = CodeReviewIssue(
                            file_name=file_name,
                            issue_description=f"Sweep has identified a redundant function: {justification}",
                            start_line=function.start_line,
                            end_line=function.end_line
                        )
                        repeated_functions_code_issues[function.file_name].append(new_code_issue)

                # now revert the cloned repo file - if this fails this can cause big issues
                try:
                    update_file(cloned_repo.repo_dir, file_name, modified_files_dict[file_name]["original"])
                    update_file(cloned_repo.cached_dir, file_name, modified_files_dict[file_name]["original"])
                except Exception as e:
                    logger.error(f"Failure updating file {cloned_repo.repo_dir}{function.file_name}: {e}")
                    posthog.capture(
                        "identify_repeated_functions", 
                        "identify_repeated_functions error reverting", 
                        properties={"error": str(e), "cloned_repo.repo_dir": cloned_repo.repo_dir, "file_name": function.file_name}
                    )
                    raise e
        return repeated_functions_code_issues

    # sorts issues by severity, potential issues are not sorted
    # returns modified code_review_by_file and a list of all issues sorted
    def sort_code_issues_by_severity(
        self,
        code_review_by_file: dict[str, CodeReview], 
        chat_logger: ChatLogger = None,
    ) -> tuple[dict[str, CodeReview], list[CodeReviewIssue]]:
        all_issues_formatted = "<all_issues>\n"
        index_to_issues: dict[int, CodeReviewIssue] = {}
        issue_index = 1
        # build all_issues string
        for file_name, code_review in code_review_by_file.items():
            all_issues = code_review.issues
            for issue in all_issues:
                all_issues_formatted += f"\n<issue index='{issue_index}'>\n{issue.issue_description}\n</issue>\n"
                index_to_issues[issue_index] = issue
                issue_index += 1
        all_issues_formatted += "\n</all_issues>"

        # if there was only one minus issue there is no need to sort anything
        if issue_index <= 2:
            return code_review_by_file, []
        
        self.messages = [
            Message(
                role="system",
                content=system_prompt_sort_issues,
            )
        ]
        formatted_user_prompt = user_prompt_sort_issues.format(all_issues=all_issues_formatted)
        sorted_issues_response = self.chat_anthropic(
            content=formatted_user_prompt,
            temperature=0.1,
            model=CLAUDE_MODEL,
            use_openai=True
        )
        if chat_logger:
            chat_logger.add_chat(
                {
                    "model": self.model,
                    "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                    "output": "END OF MESSAGES",
                })
        
        sorted_issue_indices, _ , _ = extract_object_fields_from_string(
            sorted_issues_response, ["sorted_issue_indices_by_severity"]
        )
        # parse output to reorder the issues
        sorted_indices_string = sorted_issue_indices["sorted_issue_indices_by_severity"].split(",")
        sorted_indices = []
        for index in sorted_indices_string:
            try:
                index = int(index.strip())
                _issue = index_to_issues[index]
                sorted_indices.append(index)
            except Exception as e:
                logger.error(f"Failure parsing indices in sort_code_issues_by_severity: {e}")
        # sort the issues within the CodeReview object but also create a global list of all issues
        all_issues_sorted: list[CodeReviewIssue] = []
        for index in sorted_indices:
            all_issues_sorted.append(index_to_issues[index])
        # now rebuild the issue arrays for each of the code reviews
        for file_name, code_review in code_review_by_file.items():
            code_review.issues = []
            for issue in all_issues_sorted:
                if issue.file_name == file_name:
                    code_review.issues.append(issue)
        return code_review_by_file, all_issues_sorted
        

# get the best issue to return based on group vote
@posthog_trace
def get_group_voted_best_issue_index(
    username: str, 
    file_name: str, 
    label: str, 
    files_to_labels_indexes: dict[str, dict[str, list[int]]], 
    files_to_embeddings: dict[str, any], 
    index_length: int, 
):
    similarity_scores = [0 for _ in range(index_length)]
    for index_i in range(index_length):
        for index_j in range(index_length):
            if index_i != index_j:
                embedding_i = files_to_embeddings[file_name][index_i].reshape(1,512)
                embedding_j = files_to_embeddings[file_name][index_j].reshape(1,512)
                similarity_scores[index_i] += cosine_similarity(embedding_i, embedding_j)[0][0]
    max_index = files_to_labels_indexes[file_name][label][np.argmax(similarity_scores)]
    return max_index

# function that gets the code review for every file in the pr
def get_code_reviews_for_file(
    pr_changes: dict[str, PRChange], 
    formatted_pr_changes_by_group: dict[str, GroupedFilesForReview], 
    cloned_repo: ClonedRepo,
    pull_request_info: str,
    chat_logger: ChatLogger | None = None,
    seed: int | None = None
):
    review_bot = PRReviewBot()
    code_review_by_group = review_bot.review_code_changes_by_file(
        pr_changes,
        formatted_pr_changes_by_group, 
        cloned_repo, 
        pull_request_info,
        chat_logger=chat_logger, 
        seed=seed
    )
    code_review_by_group = review_bot.review_code_issues_by_file(
        pr_changes, 
        formatted_pr_changes_by_group, 
        code_review_by_group, 
        cloned_repo, 
        pull_request_info,
        chat_logger=chat_logger, 
        seed=seed
    )
    return code_review_by_group

# run 5 seperate instances of review_pr and then group the resulting issues and only take the issues that appear the majority of the time (> 3)
@posthog_trace
def group_vote_review_pr(
    username: str, 
    pr_changes: dict[str, PRChange], 
    formatted_pr_changes_by_group: dict[str, GroupedFilesForReview],
    cloned_repo: ClonedRepo,
    pull_request_info: str,
    multiprocess: bool = True, 
    chat_logger: ChatLogger | None = None, 
) -> dict[str, CodeReview]:
    majority_code_review_by_file = {}
    code_reviews_by_group: list[dict[str, CodeReviewByGroup]] = []
    GROUP_SIZE = 5
    if multiprocess:
        chat_logger = None
        pool = multiprocessing.Pool(processes=5)
        # we have to create copies of the ClonedRepo or else the repo_dir will get cleaned up when the processes terminate
        cloned_repos = [
            MockClonedRepo(
                _repo_dir=cloned_repo.repo_dir,
                repo_full_name=cloned_repo.repo_full_name,
                installation_id=cloned_repo.installation_id,
                branch=cloned_repo.branch,
                token=cloned_repo.token,
                repo=cloned_repo.repo,
                git_repo=git.Repo(cloned_repo.repo_dir),
            ) for _ in range(GROUP_SIZE)
        ]
        results = [
            pool.apply_async(get_code_reviews_for_file, args=(
                pr_changes, 
                formatted_pr_changes_by_group,
                cloned_repos[i], 
                pull_request_info, 
                chat_logger, 
                i
            ))
            for i in range(GROUP_SIZE)
        ]
        pool.close()
        pool.join()
        for result in results:
            try:
                code_review = result.get()
                code_reviews_by_group.append(code_review)
            except Exception as e:
                logger.error(f"Error fetching result: {e}")
                posthog.capture(
                    username, 
                    "get_code_reviews_for_file error multiprocess", 
                    properties={"error": str(e)}
                )
    else:
        for i in range(GROUP_SIZE):
            review = get_code_reviews_for_file(
                pr_changes, 
                formatted_pr_changes_by_group,
                cloned_repo, 
                pull_request_info,
                chat_logger=chat_logger, 
                seed=i
            )
            code_reviews_by_group.append(review)
    # embed each issue and then cluster them
    # extract code issues for each file and prepare them for embedding
    code_reviews_ready_for_embedding = [] 
    for code_review_by_group in code_reviews_by_group:
        prepped_code_review: dict[str, list[str]] = {}
        for group_name, code_review in code_review_by_group.items():
            # using object_to_xml may not be the most optimal as it adds extra xml tags
            prepped_code_review[group_name] = [object_to_xml(code_issue, 'issue') for code_issue in code_review.issues]
        code_reviews_ready_for_embedding.append(prepped_code_review)
    
    # embed all extracted texts
    code_reviews_embeddings = []
    for prepped_code_review in code_reviews_ready_for_embedding:
        embedded_code_review: dict[str, list] = {}
        for group_name, code_issues in prepped_code_review.items():
            embedded_code_review[group_name] = embed_text_array(code_issues)
        code_reviews_embeddings.append(embedded_code_review)
    # dbscan - density based spatial clustering of app with noise
    # format: {file_name: [label1, label2, ...]}
    groups_to_labels = {}
    # corresponding issues for each file
    # format: {file_name: [issue1, issue2, ...]}
    groups_to_issues = {}
    # corresponding embeddings for each file
    # format: {file_name: [embedding1, embedding2, ...]}
    groups_to_embeddings = {}

    # for each file combine all the embeddings together while determining the max amount of clusters
    for group_name in formatted_pr_changes_by_group:
        all_embeddings = []
        all_issues = []
        for i in range(len(code_reviews_by_group)):
            embeddings = code_reviews_embeddings[i][group_name]
            code_review = code_reviews_by_group[i][group_name]
            if embeddings:
                embeddings = embeddings[0]
                for embedding in embeddings:
                    all_embeddings.append(embedding.flatten())
                    all_issues.extend(code_review.issues)
        groups_to_issues[group_name] = all_issues
        all_flattened_embeddings = np.array(all_embeddings)
        groups_to_embeddings[group_name] = all_flattened_embeddings
        # note DBSCAN expects a shape with less than or equal to 2 dimensions
        try:
            if all_flattened_embeddings.size:
                db = DBSCAN(eps=0.2, min_samples=2).fit(all_flattened_embeddings)
                groups_to_labels[group_name] = db.labels_
            else:
                groups_to_labels[group_name] = []
        except ValueError as e:
            logger.error(f"Error with dbscan {e}")
    LABEL_THRESHOLD = 4
    # get the labels that have a count greater than the threshold
    # format: {file_name: {label: [index, ...]}}
    groups_to_labels_indexes = {}
    for group_name, labels in groups_to_labels.items():
        index_dict: dict[str, list[int]] = {}
        for i, v in enumerate(labels):
            key = str(v)
            if key not in index_dict:
                index_dict[key] = []
            index_dict[key].append(i)
        groups_to_labels_indexes[group_name] = index_dict

    # create the final code_reviews_by_file
    for group_name, labels_dict in groups_to_labels_indexes.items():
        # pick first one as diff summary doesnt really matter
        final_code_review: CodeReview = copy.deepcopy(code_reviews_by_group[0][group_name])
        final_code_review.issues = []
        final_code_review.potential_issues = []
        final_issues = []
        potential_issues = []
        for label, indexes in labels_dict.items():
            index_length = len(indexes)
            # -1 is considered as noise
            if index_length >= LABEL_THRESHOLD and label != "-1":
                max_index = get_group_voted_best_issue_index(username, group_name, label, groups_to_labels_indexes, groups_to_embeddings, index_length)
                # add to final issues, first issue - TODO use similarity score of all issues against each other
                final_issues.append(groups_to_issues[group_name][max_index])
            # get potential issues which are one below the label_threshold
            if index_length == LABEL_THRESHOLD - 1 and label != "-1":
                max_index = get_group_voted_best_issue_index(username, group_name, label, groups_to_labels_indexes, groups_to_embeddings, index_length)
                potential_issues.append(groups_to_issues[group_name][max_index])
        final_code_review.issues = final_issues
        final_code_review.potential_issues = potential_issues
        majority_code_review_by_file[group_name] = copy.deepcopy(final_code_review)
    return majority_code_review_by_file

@posthog_trace
def review_pr_detailed_checks(
    username: str, 
    cloned_repo: ClonedRepo,
    pr_changes: dict[str, PRChange], 
    code_review_by_file: dict[str, CodeReview], 
    pull_request_info: str,
    chat_logger: ChatLogger | None = None, 
) -> dict[str, CodeReview]:
    review_bot = PRReviewBot()
    # get a list of newly created functions
    newly_created_functions_dict: dict[str, list[FunctionDef]] = review_bot.identify_functions_in_patches(
        pr_changes, chat_logger=chat_logger
    )
    new_code_issues: dict[str, list[CodeReviewIssue]] = review_bot.identify_repeated_functions(
        cloned_repo, newly_created_functions_dict, pull_request_info, chat_logger=chat_logger
    )
    # now append these code issues to the existing ones
    for file_name, new_code_issues in new_code_issues.items():
        if new_code_issues:
            code_review_by_file[file_name].issues.extend(new_code_issues)
    
    return code_review_by_file

# get the summary for a pr given all the changes
def get_pr_summary_from_patches(
    pr_changes: dict[str, PRChange], 
    chat_logger: ChatLogger | None = None
):
    review_bot = PRReviewBot()
    formatted_pr_patches = ""
    for file_name, pr_change in pr_changes.items():
        patches = format_patches_for_pr_change(pr_change)
        formatted_pr_patches += f'\n\n<patches file_name="{file_name}">\n{patches}\n</patches>\n\n'
    pr_summary = review_bot.get_pr_summary(formatted_pr_patches, chat_logger=chat_logger)
    return pr_summary
    
@posthog_trace
def sort_code_issues_by_severity(
    username: str, 
    code_review_by_file: dict[str, CodeReview], 
    chat_logger: ChatLogger | None = None, 
) -> dict[str, CodeReview]:
    review_bot = PRReviewBot()
    MAX_ISSUE_AMOUNT = 10
    # sort all the issues by severity
    code_review_by_file, all_issues_sorted = review_bot.sort_code_issues_by_severity(
        code_review_by_file, chat_logger=chat_logger
    )
    all_issues_sorted = all_issues_sorted[:MAX_ISSUE_AMOUNT]
    
    return code_review_by_file, all_issues_sorted

def format_pr_info(pr: PullRequest):
    info = ""
    try:
        title = pr.title
        if title:
            info += f"<pr_title>\n{title}\n<\pr_title>\n\n"
    except Exception as e:
        logger.warning(f"Couldn't fetch title for pr: {pr}\nError: {e}")
    try:
        description = pr.body
        if description:
            info += f"<pr_description>\n{description}\n</pr_description>\n\n"
    except Exception as e:
        logger.warning(f"Couldn't fetch body for pr: {pr}\nError: {e}")
    return info

# cluster patches based on similarity and review based off of that
def cluster_patches(pr_changes: dict[str, PRChange]):
    all_patches_by_file: dict[str, list[Patch]] = {}
    all_patch_strings_by_file: dict[str, str] = {}
    for file_name, pr_change in pr_changes.items():
        all_patches_by_file[file_name] = pr_change.patches
        all_patch_strings_by_file[file_name] = objects_to_xml(
            pr_change.patches, 
            "patch", 
            "patches",
            exclude_fields=['old_start', 'new_start', 'old_count', 'new_count']
        )
    # get the order of the files
    file_order = [file_name for file_name in all_patch_strings_by_file.keys()]
    files_to_embed = [patches for patches in all_patch_strings_by_file.values()]
    embedded_patches = embed_text_array(files_to_embed)[0]
    db = DBSCAN(eps=0.6, min_samples=2).fit(embedded_patches)
    labels = db.labels_
    # group key is the label, value is the list of file names to review together
    groups_to_review_files_in: dict[str, list[str]] = {}
    # split files into their groups -> -1 means create a seperate group -1x for that group
    noise_groups = 0
    for index, group in enumerate(labels):
        if group != -1:
            group_key = str(group)
        else:
            group_key = str(group) + str(noise_groups)
            noise_groups += 1
        if group_key not in groups_to_review_files_in:
            groups_to_review_files_in[group_key] = []
        groups_to_review_files_in[group_key].append(file_order[index])

    return groups_to_review_files_in

def decompose_code_review_by_group(
    code_reviews_by_group: dict[str, CodeReviewByGroup]
):
    code_review_by_file: dict[str, CodeReview] = {}
    for group_name, code_review_by_group in code_reviews_by_group.items():
        file_names = code_review_by_group.file_names
        for file_name in file_names:
            issues = [issue for issue in code_review_by_group.issues if issue.file_name == file_name]
            potential_issues = [issue for issue in code_review_by_group.potential_issues if issue.file_name == file_name]
            code_review = CodeReview(
                file_name=file_name,
                diff_summary=code_review_by_group.diff_summary,
                issues=issues,
                potential_issues=potential_issues
            )
            code_review_by_file[file_name] = code_review
    return code_review_by_file