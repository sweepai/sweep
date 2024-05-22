"""
Take a PR and provide an AI generated review of the PR.
"""
import copy
import multiprocessing
import re

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
from sweepai.dataclasses.codereview import CodeReview, CodeReviewIssue, FunctionDef, PRChange, Patch
from sweepai.logn.cache import file_cache
from sweepai.utils.event_logger import logger, posthog
from sweepai.utils.chat_logger import ChatLogger
from github.Repository import Repository
from github.PullRequest import PullRequest

from sweepai.utils.github_utils import ClonedRepo, update_file
from sweepai.utils.str_utils import add_line_numbers, extract_object_fields_from_string, extract_objects_from_string, object_to_xml, objects_to_xml, remove_lines_from_text
from sweepai.utils.ticket_rendering_utils import parse_issues_from_code_review
from sweepai.utils.ticket_utils import get_top_k_snippets

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
def get_pr_changes(repo: Repository, pr: PullRequest) -> tuple[list[PRChange], list[str]]:
    sweep_config: SweepConfig = SweepConfig()
    base_sha = pr.base.sha
    head_sha = pr.head.sha

    comparison = repo.compare(base_sha, head_sha)
    file_diffs = comparison.files

    pr_diffs = []
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
            except Exception as e_:
                e = e_
                errored = True
                unsuitable_files.append((file_name, e))
        if file.status == "removed":
            new_code = ""
        else:
            try:
                new_code = safe_decode(repo=repo, path=file.filename, ref=head_sha)
            except Exception as e_:
                e = e_
                errored = True
                unsuitable_files.append((file_name, e))

        # drop unsuitable files
        if new_code: 
            suitable, reason = sweep_config.is_file_suitable(new_code)
            if not suitable:
                errored = True
                e = UnsuitableFileException(e)
                unsuitable_files.append((file_name, e))

        if errored:
            posthog.capture(
                "get_pr_changes", 
                "get_pr_changes error", 
                properties={"error": str(e), "file_name": file_name}
            )
            continue

        status = file.status
        pr_change = PRChange(
            file_name=file_name,
            diff=diff,
            old_code=old_code,
            new_code=new_code,
            status=status,
            patches=split_diff_into_patches(diff)
        )
        diff_annotations = get_diff_annotations(
            source_code=pr_change.new_code,
            diffs=[patch.changes for patch in pr_change.patches],
            file_name=pr_change.file_name
        )
        pr_change.annotations = diff_annotations
        pr_diffs.append(
            pr_change
        )
    return pr_diffs, dropped_files, unsuitable_files

def split_diff_into_patches(diff: str) -> list[Patch]:
    patches = []
    hunks = re.findall(r'@@ -\d+,\d+ \+\d+,\d+ @@.*?(?=\n@@ -|\Z)', diff, re.DOTALL)
    for hunk in hunks:
        line_numbers = re.findall(r'-(\d+),(\d+) \+(\d+),(\d+)', hunk)
        if line_numbers:
            old_start, old_count, new_start, new_count = map(int, line_numbers[0])
            changes = hunk[hunk.index('@@'):].strip()
            patch = Patch(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                changes=changes
            )
            patches.append(patch)
    return patches

pr_changes_prefix = "The following changes were made in the PR. Each change contains all of the patches that were applied to a file, as well as the source code after the change.\n"

pr_change_unformatted = """\
<pr_change file_name="{file_name}">
<file_patches>
{patches}
</file_patches>
</pr_change>"""

pr_change_with_source_code_unformatted = """\
<pr_change file_name="{file_name}">
<file_patches>
{patches}
</file_patches>

And here is the full source code after applying the pull request changes:
<source_code>
{file_contents}
</source_code>
</pr_change>"""

patch_format = """\
<patch file_name="{file_name}" index="{index}">
{diff}
</patch>
<patch_annotation file_name="{file_name}" index="{index}">
{annotation}
</patch_annotation>"""

# format only the patches for the PRChange
def format_patches_for_pr_change(pr_change: PRChange):
    patches = ""
    for idx, patch in enumerate(pr_change.patches):
        patches += patch_format.format(
            file_name=pr_change.file_name,
            index=idx + 1,
            diff=patch.changes,
            annotation=pr_change.annotations[idx]
        )
        if idx < len(pr_change.patches) - 1:
            patches += "\n"
    return patches

def format_pr_change(pr_change: PRChange, pr_idx: int=0):
    patches = format_patches_for_pr_change(pr_change)
    return pr_change_with_source_code_unformatted.format(
        file_name=pr_change.file_name,
        patches=patches,
        file_contents=add_line_numbers(pr_change.new_code, start=1)
    )

def format_pr_changes_by_file(pr_changes: list[PRChange]) -> dict[str, str]:
    formatted_pr_changes_by_file = {}
    for idx, pr_change in enumerate(pr_changes):
        formatted_pr_changes_by_file[pr_change.file_name] = format_pr_change(pr_change, idx)
    return formatted_pr_changes_by_file

system_prompt = """You are a careful and smart tech lead that wants to avoid production issues. You will be analyzing a set of diffs representing a pull request made to a piece of source code. Be very concise."""

system_prompt_review = """You are a busy tech manager who is responsible for reviewing prs and identifying any possible production issues. 
You will be analyzing a list of potential issues that have been identified by a previous engineer and determing which issues are severe enough to bring up to the original engineer."""

system_prompt_identify_new_functions = """You are an expert programmer with a keen eye for detail, assigned to analyze a series of code patches in a pull request. Your primary responsibility is to meticulously identify all newly defined functions within the code."""

system_prompt_identify_repeats = """You are a proficient programmer tasked with identifying repeated or unnecessary functions in a codebase. Your job is to find and highlight any duplicated or redundant function definitions.
You will be given a function definition that was just added to the codebase and your job will be to check whether or not this function was actually necessary or not given a series of code snippets.
"""

user_prompt = """\
# Code Review
Here are the changes in the pull request diffs:
<diffs>
{diff}
</diffs>

# Instructions
1. Analyze the code changes.
    1a. Review each diff/patch individually, examining the code changes line-by-line.
    1b. For each line of code changed, consider:
        - What is the purpose of this line of code?
        - How does this line of code interact with or impact the rest of the codebase?
        - Is this line of code functionally correct? Could it introduce any bugs or errors?
        - Is this line of code necessary? Or could it be an accidental change or commented out code?
    1c. Describe all changes that were made in the diffs. Respond in the following format. (1 paragraph)
<thoughts>
<thinking>
{{Analysis of diff/patch 1}}
</thinking>
...
</thoughts>
    1d. Provide a final summary for this file that should be a single sentence and formatted within a <diff_summary> tag.
Here is an example, make sure the summary sounds natural and keep it brief and easy to skim over:
<example_diff_summary>
Added a new categorization system for snippets in `multi_prep_snippets` and updated the snippet score calculation in `get_pointwise_reranked_snippet_scores`. 
</example_diff_summary>
<diff_summary>
{{Final summary of the major changes}}
</diff_summary>

2. Identify all issues.
    2a. Determine whether there are any functional issues, bugs, edge cases, or error conditions that the code changes introduce or fail to properly handle. Consider the line-by-line analysis from step 1b. (1 paragraph)
    2b. Determine whether there are any security vulnerabilities or potential security issues introduced by the code changes. (1 paragraph) 
    2c. Identify any other potential issues that the code changes may introduce that were not captured by 2a or 2b. This could include accidental changes such as commented out code. (1 paragraph)
    2d. Only include issues that you are very confident will cause serious issues that prevent the pull request from being merged. For example, focus only on functional code changes and ignore changes to strings and comments that are purely descriptive.
    2e. Format the found issues and root causes using the following XML tags. Each issue description should be a single sentence. Include the corresponding start and end line numbers of the patch, these line numbers should be at most 50 apart. DO NOT reference the patch or patch number in the description. Format these fields in an <issue> tag in the following manner:
<issues>
<issue>
<issue_description>
{{Issue 1 description}}
</issue_description>
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

user_prompt_review = """
Below are a series of identified issues for the file {file_name} formatted in the following way:
<potential_issues>
<issue>
<issue_description>
{{Issue 1 description}}
</issue_description>
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

# Instructions
1. Analyze each identified potential issue for the file {file_name}
    1a. Review each identified issue individually, formulate 3-5 questions to answer in order to determine the severity of the issue.
    1b. Answer the questions formulated in step 1a. In order to accomplish this examine the referenced lines of code in the provided code files above.
    1c. Answer the following questions in addition to the ones you generated in steps 1a. Is this reported issue accurate (double check that the previous reviewer was not mistaken, YOU MUST include the corresponding patch for proof)? If the answer to this question is no, then the issue is not severe. 
    1d. Determine whether or not this issue is severe enough to prevent the pull request from being merged or not. For example, any potential logical error is considered severe.
    1e. Take note of some common issues: Accidently removing or commenting out lines of code that has functional utility. In this case double check if this change was intentional or accidental.
    1f. Deliver your analysis in the following format:
<thoughts>
<thinking>
{{Analysis of the issue, include ALL the questions and answers}}
</thinking>
...
</thoughts>

2. Decide which issues to keep
    2a. Based on your analysis in step 1, now decide which issues to keep and drop. Only include severe issues.
    2b. After choosing to keep an issue you are to respond in the following format:
<severe_issues>
<issue>
<issue_description>
{{Issue 1 description}}
</issue_description>
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

user_prompt_identify_new_functions = """Below are all the patches made to the file {file_name} in this pull request. Use these patches to determine if there are any newly defined functions.
# PR Patches

{patches}

Below is the file {file_name} with all the above patches applied along with the line numbers. Use this to identify the correct starting and ending line numbers.
# Relevant code file with line numbers

{numbered_code_file}

# Instructions
1. Analyze each of the patches above and identify ALL newly defined functions.
    1a. Note that if a function is renamed, or has some of its parameters changed, this should not be included as a newly defined function.
    1b. All newly defined functions should mean that the function is ENTIRELY new and must have been coded from scratch.
2. Return the list of all newly defined functions in the following xml format:
<newly_defined_functions>
<function>
<function_code>
{{Function code copied verbatim for the patch}}
<function_code>
<start_line>
{{Corresponding starting line number for function 1 (inclusive)}}
</start_line>
<end_line>
{{Corresponding ending line number for function 1 (inclusive)}}
</end_line>
</function>
...
</newly_defined_functions>
"""

user_prompt_identify_repeats = """
Below is the function definition that was just added to the code base.
# New Function

{function}

Below are a series of code snippets retrieved from the codebase via vector search. Analyze these code snippets to see if there are any similar functions that render the new function obselete and redundant.
# Relevant code snippets

{formatted_code_snippets}

# Instructions
1. Analyze each of the code snippets above and determine whether or not the new function is really necessary or not. Specifically, compare the new function with the existing methods in the code snippets by answering ALL the following questions:
   1a. Purpose: What is the primary purpose of the new function? Is this purpose already served by existing methods? Is the purpose of this function to solely call other functions which allows for cleaner code? If the answer the the last question of 1a is yes, the new function should not be removed.
   1b. Functionality: What specific tasks or operations does the new function perform? Are these tasks or operations already handled by existing methods?
   1c. Initialization: What data structures or variables are initialized in the new function? Are similar initializations present in existing methods?
   1d. Data Processing: How does the new function process data (e.g., formatting, extracting, or transforming data)? Are these data processing steps already implemented in existing methods?
   1e. Unique Contributions: Does the new function provide any unique contributions or improvements that are not covered by existing methods? If it does then it should be considered as not redundant and should be kept.
   1f. Impact of Removal: Would removing this function require a significant refactor of existing functions? Would the use cases of the existing functions change at all? If the answer is yes to any of these questions the new function should be kept.

2. Return your answer in the following xml format:
<redundant_new_function>
<thinking>
{{Any thoughts/analysis you have should go here. This is where you MUST answer each of the questions above.}}
</thinking>
<answer>
{{'true' if the new function is redundant/repeated/obsolete, 'false' if the new function is needed}}
</answer>
<justification>
{{A very brief justification of the decision made. When justifying why make sure to reference relevant functions. Max 1-2 sentences.}}
</justification>
<solution>
{{Provide a brief description of how you would fix the issue of having this redundant function. Include code snippets as examples. Do not include this section if the answer was 'false'}}
</solution>
</redundant_new_function>"""

CLAUDE_MODEL = "claude-3-opus-20240229"

class PRReviewBot(ChatGPT):
    # fetch all potential issues for each file based on the diffs of that file
    def review_code_changes_by_file(self, pr_changes_by_file: dict[str, str], chat_logger: ChatLogger = None, seed: int | None = None):
        code_reviews_by_file = {}
        for file_name, pr_changes in pr_changes_by_file.items():
            self.messages = [
                Message(
                    role="system",
                    content=system_prompt,
                )
            ]
            formatted_user_prompt = user_prompt.format(diff=pr_changes)
            code_review_response = self.chat_anthropic(
                content=formatted_user_prompt,
                temperature=0,
                model=CLAUDE_MODEL,
                use_openai=True,
                seed=seed
            )
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
            code_reviews_by_file[file_name] = CodeReview(file_name=file_name, diff_summary=diff_summary, issues=potential_issues, potential_issues=[])
            if chat_logger:
                chat_logger.add_chat(
                    {
                        "model": self.model,
                        "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                        "output": "END OF MESSAGES",
                    })
        return code_reviews_by_file

    # review the generated issues more critically for each file to see if they are actually important or not
    def review_code_issues_by_file(
        self, 
        pr_changes: list[PRChange], 
        formatted_pr_changes_by_file: dict[str, str], 
        code_reviews_by_file: dict[str, CodeReview], 
        chat_logger: ChatLogger = None,
        seed: int | None = None
    ):
        files_to_patches: dict[str, str] = {}
        # format all patches for all files
        for pr_change in pr_changes:
            patches = format_patches_for_pr_change(pr_change)
            files_to_patches[pr_change.file_name] = patches

        # go file by file
        for file_name, code_review in code_reviews_by_file.items():
            self.messages = [
                Message(
                    role="system",
                    content=system_prompt_review,
                )
            ]
            # if no issues were identified continue to next file
            if not code_review.issues:
                continue
            # convert our CodeReviewIssue list to an xml string
            potential_issues_string = objects_to_xml(code_review.issues, "issue", outer_field_name="potential_issues")
            # now prepend all other pr changes to the current pr change
            all_other_pr_changes = "\n\n".join([pr_change_unformatted.format(file_name=file, patches=patches) for file, patches in files_to_patches.items() if file != file_name])
            
            formatted_user_prompt = user_prompt_review.format(file_name=file_name, potential_issues=potential_issues_string, pr_changes=f"{all_other_pr_changes}\n{formatted_pr_changes_by_file[file_name]}")
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
            code_reviews_by_file[file_name].issues = potential_issues
            
            if chat_logger:
                chat_logger.add_chat(
                    {
                        "model": self.model,
                        "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                        "output": "END OF MESSAGES",
                    })
        return code_reviews_by_file

    # given a list of changes identify newly defined functions
    def identify_functions_in_patches(
        self,
        pr_changes: list[PRChange],
        chat_logger: ChatLogger | None = None
    ):
        newly_created_functions: dict[str, list[FunctionDef]] = {}
        files_to_patches: dict[str, str] = {}
        files_to_pr_change: dict[str, PRChange] = {}
        # format all patches for all files
        for pr_change in pr_changes:
            patches = format_patches_for_pr_change(pr_change)
            files_to_patches[pr_change.file_name] = patches
            files_to_pr_change[pr_change.file_name] = pr_change
        # go file by file
        for file_name, patches in files_to_patches.items():
            pr_change = files_to_pr_change[file_name]
            self.messages = [
                Message(
                    role="system",
                    content=system_prompt_identify_new_functions,
                )
            ]

            formatted_user_prompt = user_prompt_identify_new_functions.format(
                file_name=file_name, patches=patches, numbered_code_file=add_line_numbers(files_to_pr_change[file_name].new_code, start=1))
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
            newly_defined_functions_regex = r'<newly_defined_functions>(?P<content>.*?)<\/newly_defined_functions>'
            newly_defined_functions_match = re.search(newly_defined_functions_regex, new_functions_response, re.DOTALL)
            if newly_defined_functions_match:
                extracted_functions, _ = extract_objects_from_string(newly_defined_functions_match.group("content"), "function", function_def_params)
                patches = pr_change.patches
                for extracted_function in extracted_functions:
                    # do some basic double checking, make sure the start and end lines make sense
                    # the start and end lines should fall within the start and end of one patch, if they dont, then it is clearly wrong
                    start = int(extracted_function.get('start_line', -1))
                    end = int(extracted_function.get('end_line', -1))
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
        chat_logger: ChatLogger | None = None
    ) -> dict[str, list[CodeReviewIssue]]:
        repeated_functions_code_issues: dict[str, list[CodeReviewIssue]] = {}
        for file_name, newly_created_functions in newly_created_functions_dict.items():
            # keep copy of edited files to revert later
            modified_files_dict: dict[str, dict[str, str]] = {}
            modified_files_dict[file_name] = {"original": cloned_repo.get_file_contents(file_name)}
            repeated_functions_code_issues[file_name] = []
            # do a similarity search over the chunked code base to see if the function name matches anything
            for function in newly_created_functions:
                # remove the function definition from the file to prevent biased results
                modified_files_dict[file_name]["modified"] = remove_lines_from_text(
                    modified_files_dict[file_name]["original"],start=int(function.start_line),end=int(function.end_line)
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
                # get the top five snippets and then pass those into sweep to ask if there are any repeated function definitions
                ranked_snippets, _, _ = get_top_k_snippets(
                    cloned_repo, function.function_code, None, k=5, include_docs=True, include_tests=False, do_not_use_file_cache=True
                )
                formatted_code_snippets = "\n\n".join(
                    [f"<code_snippet file_name='{snippet.file_path}' snippet_index='{idx}'>\n{snippet.get_snippet()}\n</code_snippet>" for idx, snippet in enumerate(ranked_snippets)]
                )
                formatted_user_prompt = user_prompt_identify_repeats.format(
                    function=f"<new_function>\n{function.function_code}\n</new_function>", formatted_code_snippets=formatted_code_snippets
                )
                self.messages = [
                    Message(
                        role="system",
                        content=system_prompt_identify_repeats,
                    )
                ]
                repeated_functions_response = self.chat_anthropic(
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
                repeated_function_params = ['answer', 'justification', 'solution']
                repeated_function, _, failed_param = extract_object_fields_from_string(repeated_functions_response, repeated_function_params)
                # if extraction fails
                if failed_param == "answer":
                    logger.error(f"Failure in extract_object_fields_from_string: {repeated_functions_response}")
                    posthog.capture(
                        "extract_object_fields_from_string", "extract_object_fields_from_string failed", properties={"text": repeated_functions_response, "params": str(repeated_function_params)}
                    )
                else:
                    # case insensitive match
                    answer_true = r'true'
                    if bool(re.search(answer_true, repeated_function['answer'], re.IGNORECASE)):
                        justification = repeated_function.get("justification", "")
                        new_code_issue = CodeReviewIssue(
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
    pr_changes: list[PRChange], 
    formatted_pr_changes_by_file: dict[str, str], 
    chat_logger: ChatLogger | None = None,
    seed: int | None = None
):
    review_bot = PRReviewBot()
    code_review_by_file = review_bot.review_code_changes_by_file(formatted_pr_changes_by_file, chat_logger=chat_logger, seed=seed)
    code_review_by_file = review_bot.review_code_issues_by_file(pr_changes, formatted_pr_changes_by_file, code_review_by_file, chat_logger=chat_logger, seed=seed)
    return code_review_by_file

# run 5 seperate instances of review_pr and then group the resulting issues and only take the issues that appear the majority of the time (> 3)
@posthog_trace
def group_vote_review_pr(
    username: str, 
    pr_changes: list[PRChange], 
    formatted_pr_changes_by_file: dict[str, str], 
    multiprocess: bool = True, 
    chat_logger: ChatLogger | None = None, 
) -> dict[str, CodeReview]:
    majority_code_review_by_file = {}
    code_reviews_by_file = []
    GROUP_SIZE = 5
    if multiprocess:
        chat_logger = None
        pool = multiprocessing.Pool(processes=5)
        results = [
            pool.apply_async(get_code_reviews_for_file, args=(pr_changes, formatted_pr_changes_by_file, chat_logger, i))
            for i in range(GROUP_SIZE)
        ]
        pool.close()
        pool.join()
        for result in results:
            try:
                code_review = result.get()
                code_reviews_by_file.append(code_review)
            except Exception as e:
                logger.error(f"Error fetching result: {e}")
                posthog.capture(
                    username, 
                    "get_code_reviews_for_file error multiprocess", 
                    properties={"error": str(e)}
                )
    else:
        for i in range(GROUP_SIZE):
            code_reviews_by_file.append(get_code_reviews_for_file(pr_changes, formatted_pr_changes_by_file, chat_logger=chat_logger, seed=i))
    
    # embed each issue and then cluster them
    # extract code issues for each file and prepare them for embedding
    code_reviews_ready_for_embedding = [] 
    for code_review_by_file in code_reviews_by_file:
        prepped_code_review = {}
        for file_name, code_review in code_review_by_file.items():
            # using object_to_xml may not be the most optimal as it adds extra xml tags
            prepped_code_review[file_name] = [object_to_xml(code_issue, 'issue') for code_issue in code_review.issues]
        code_reviews_ready_for_embedding.append(prepped_code_review)
    
    # embed all extracted texts
    code_reviews_embeddings = []
    for prepped_code_review in code_reviews_ready_for_embedding:
        embedded_code_review = {}
        for file_name, code_issues in prepped_code_review.items():
            embedded_code_review[file_name] = embed_text_array(code_issues)
        code_reviews_embeddings.append(embedded_code_review)
    # dbscan - density based spatial clustering of app with noise
    # format: {file_name: [label1, label2, ...]}
    files_to_labels = {}
    # corresponding issues for each file
    # format: {file_name: [issue1, issue2, ...]}
    files_to_issues = {}
    # corresponding embeddings for each file
    # format: {file_name: [embedding1, embedding2, ...]}
    files_to_embeddings = {}

    # for each file combine all the embeddings together while determining the max amount of clusters
    for file_name in formatted_pr_changes_by_file:
        all_embeddings = []
        all_issues = []
        for i in range(len(code_reviews_by_file)):
            embeddings = code_reviews_embeddings[i][file_name]
            code_review = code_reviews_by_file[i][file_name]
            if embeddings:
                embeddings = embeddings[0]
                for embedding in embeddings:
                    all_embeddings.append(embedding.flatten())
                    all_issues.extend(code_review.issues)
        files_to_issues[file_name] = all_issues
        all_flattened_embeddings = np.array(all_embeddings)
        files_to_embeddings[file_name] = all_flattened_embeddings
        # note DBSCAN expects a shape with less than or equal to 2 dimensions
        try:
            if all_flattened_embeddings.size:
                db = DBSCAN(eps=0.5, min_samples=3).fit(all_flattened_embeddings)
                files_to_labels[file_name] = db.labels_
            else:
                files_to_labels[file_name] = []
        except ValueError as e:
            logger.error(f"Error with dbscan {e}")
        
    LABEL_THRESHOLD = 4
    # get the labels that have a count greater than the threshold
    # format: {file_name: {label: [index, ...]}}
    files_to_labels_indexes = {}
    for file_name, labels in files_to_labels.items():
        index_dict: dict[str, list[int]] = {}
        for i, v in enumerate(labels):
            key = str(v)
            if key not in index_dict:
                index_dict[key] = []
            index_dict[key].append(i)
        files_to_labels_indexes[file_name] = index_dict

    # create the final code_reviews_by_file
    for file_name, labels_dict in files_to_labels_indexes.items():
        # pick first one as diff summary doesnt really matter
        final_code_review: CodeReview = copy.deepcopy(code_reviews_by_file[0][file_name])
        final_code_review.issues = []
        final_code_review.potential_issues = []
        final_issues = []
        potential_issues = []
        for label, indexes in labels_dict.items():
            index_length = len(indexes)
            # -1 is considered as noise
            if index_length >= LABEL_THRESHOLD and label != "-1":
                max_index = get_group_voted_best_issue_index(username, file_name, label, files_to_labels_indexes, files_to_embeddings, index_length)
                # add to final issues, first issue - TODO use similarity score of all issues against each other
                final_issues.append(files_to_issues[file_name][max_index])
            # get potential issues which are one below the label_threshold
            if index_length == LABEL_THRESHOLD - 1 and label != "-1":
                max_index = get_group_voted_best_issue_index(username, file_name, label, files_to_labels_indexes, files_to_embeddings, index_length)
                potential_issues.append(files_to_issues[file_name][max_index])
        final_code_review.issues = final_issues
        final_code_review.potential_issues = potential_issues
        majority_code_review_by_file[file_name] = copy.deepcopy(final_code_review)
    return majority_code_review_by_file

@posthog_trace
def review_pr_detailed_checks(
    username: str, 
    cloned_repo: ClonedRepo,
    pr_changes: list[PRChange], 
    code_review_by_file: dict[str, CodeReview], 
    chat_logger: ChatLogger | None = None, 
) -> dict[str, CodeReview]:
    review_bot = PRReviewBot()
    # get a list of newly defined functions
    newly_created_functions_dict: dict[str, list[FunctionDef]] = review_bot.identify_functions_in_patches(pr_changes, chat_logger=chat_logger)
    new_code_issues: dict[str, list[CodeReviewIssue]] = review_bot.identify_repeated_functions(
        cloned_repo, newly_created_functions_dict, chat_logger=chat_logger
    )
    # now append these code issues to the existing ones
    for file_name, new_code_issues in new_code_issues.items():
        if new_code_issues:
            code_review_by_file[file_name].issues.extend(new_code_issues)
    
    return code_review_by_file
    