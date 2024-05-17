"""
Take a PR and provide an AI generated review of the PR.
"""
import re

from tqdm import tqdm
from sweepai.config.client import SweepConfig
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.review_annotations import get_diff_annotations
from sweepai.core.sweep_bot import safe_decode
from sweepai.dataclasses.codereview import CodeReview, PRChange, Patch
from sweepai.logn.cache import file_cache
from sweepai.utils.event_logger import logger
from sweepai.utils.chat_logger import ChatLogger
from github.GithubException import GithubException
from github.Repository import Repository
from github.PullRequest import PullRequest

from sweepai.utils.str_utils import add_line_numbers, objects_to_xml
from sweepai.utils.ticket_rendering_utils import parse_issues_from_code_review

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

@file_cache()
def get_pr_changes(repo: Repository, pr: PullRequest) -> list[PRChange]:
    sweep_config: SweepConfig = SweepConfig()
    base_sha = pr.base.sha
    head_sha = pr.head.sha

    comparison = repo.compare(base_sha, head_sha)
    file_diffs = comparison.files

    pr_diffs = []
    for file in tqdm(file_diffs, desc="Annotating diffs"):
        file_name = file.filename
        diff = file.patch
        # we can later migrate this to use a cloned repo and fetch off of two hashes
        previous_filename = file.previous_filename or file.filename

        # drop excluded files: for example package-lock.json files
        if sweep_config.is_file_excluded(file_name):
            continue

        if file.status == "added":
            old_code = ""
        else:
            try:
                old_code = safe_decode(repo=repo, path=previous_filename, ref=base_sha)
            except GithubException:
                old_code = ""
        if file.status == "removed":
            new_code = ""
        else:
            new_code = safe_decode(repo=repo, path=file.filename, ref=head_sha)
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
    return pr_diffs

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

def format_pr_changes_by_file(pr_changes: list[PRChange]):
    formatted_pr_changes_by_file = {}
    for idx, pr_change in enumerate(pr_changes):
        formatted_pr_changes_by_file[pr_change.file_name] = format_pr_change(pr_change, idx)
    return formatted_pr_changes_by_file

system_prompt = """You are a careful and smart tech lead that wants to avoid production issues. You will be analyzing a set of diffs representing a pull request made to a piece of source code. Be very concise."""

system_prompt_review = """You are a busy tech manager who is responsible for reviewing prs and identifying any possible production issues. 
You will be analyzing a list of potential issues that have been identified by a previous engineer and determing which issues are severe enough to bring up to the original engineer."""

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
    1d. Provide a final summary for this file that should be a single sentence and formatted within a <diff_summary> tag.:
<diff_summary>
{{Final summary of changes}}
</diff_summary>

2. Identify all issues.
    2a. Determine whether there are any functional issues, bugs, edge cases, or error conditions that the code changes introduce or fail to properly handle. Consider the line-by-line analysis from step 1b. (1 paragraph)
    2b. Determine whether there are any security vulnerabilities or potential security issues introduced by the code changes. (1 paragraph) 
    2c. Identify any other potential issues that the code changes may introduce that were not captured by 2a or 2b. This could include accidental changes such as commented out code. (1 paragraph)
    2d. Only include issues that you are very confident will cause serious issues that prevent the pull request from being merged. For example, focus only on functional code changes and ignore changes to strings and comments that are purely descriptive.
    2e. Format the found issues and root causes using the following XML tags. Each issue description should be a single sentence. Include the corresponding start and end line numbers, these line numbers should only include lines of code that have been changed. DO NOT reference the patch or patch number in the description. Format these fields in an <issue> tag in the following manner:
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
    1c. Determine whether or not this issue is severe enough to prevent the pull request from being merged or not. For example, any potential logical error is considered severe.
    1d. Take note of some common issues: Accidently removing or commenting out lines of code that has functional utility. In this case double check if this change was intentional or accidental.
    1e. Deliver your analysis in the following format:
<thoughts>
<thinking>
{{Analysis of the issue, include the questions and answers}}
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

CLAUDE_MODEL = "claude-3-opus-20240229"

class PRReviewBot(ChatGPT):
    # fetch all potential issues for each file based on the diffs of that file
    def review_code_changes_by_file(self, pr_changes_by_file: dict[str, str], chat_logger: ChatLogger = None):
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
                use_openai=True
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
            code_reviews_by_file[file_name] = CodeReview(file_name=file_name, diff_summary=diff_summary, issues=potential_issues)
            if chat_logger:
                chat_logger.add_chat(
                    {
                        "model": self.model,
                        "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                        "output": "END OF MESSAGES",
                    })
        return code_reviews_by_file

    # review the generated issues more critically for each file to see if they are actually important or not
    def review_code_issues_by_file(self, pr_changes: list[PRChange], formatted_pr_changes_by_file: dict[str, str], code_reviews_by_file: dict[str, CodeReview], chat_logger: ChatLogger = None):
        files_to_patches = {}
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
                use_openai=True
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