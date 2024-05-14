"""
Take a PR and provide an AI generated review of the PR.
"""
from dataclasses import dataclass
import re

from tqdm import tqdm
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.review_annotations import get_diff_annotations
from sweepai.core.sweep_bot import safe_decode
from sweepai.logn.cache import file_cache
from sweepai.utils.event_logger import logger
from sweepai.utils.chat_logger import ChatLogger
from github.Repository import Repository
from github.PullRequest import PullRequest

from sweepai.utils.str_utils import add_line_numbers

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

@dataclass
class Patch:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    changes: str

@dataclass
class PRChange:
    file_name: str
    diff: str
    old_code: str
    new_code: str
    status: str
    patches: list[Patch]
    annotations: list[str] = None

@file_cache()
def get_pr_changes(repo: Repository, pr: PullRequest) -> list[PRChange]:
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
        old_code = safe_decode(repo=repo, path=previous_filename, ref=base_sha)
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

def format_pr_change(pr_change: PRChange, pr_idx: int=0):
    patches = ""
    for idx, patch in enumerate(pr_change.patches):
        patches += "\n" + patch_format.format(
            file_name=pr_change.file_name,
            index=idx + 1,
            diff=patch.changes,
            annotation=pr_change.annotations[idx]
        )
    return pr_change_unformatted.format(
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
    1c. Describe the key changes that were made in the diffs. (1 paragraph)
    1d. Format your response using the following XML tags. Each summary should be a single sentence and formatted within a <diff_summary> tag.:
<diff_summaries>
<diff_summary>
{{Summary of changes}}
</diff_summary>
...
</diff_summaries>

2. Identify all issues.
    2a. Determine whether there are any functional issues, bugs, edge cases, or error conditions that the code changes introduce or fail to properly handle. Consider the line-by-line analysis from step 1b. (1 paragraph)
    2b. Determine whether there are any security vulnerabilities or potential security issues introduced by the code changes. (1 paragraph) 
    2c. Identify any other potential issues that the code changes may introduce that were not captured by 2a or 2b. This could include accidental changes, commented out code, or other suspicious modifications. (1 paragraph)
    2d. Format the found issues and root causes using the following XML tags. Each issue description should be a single sentence. Include the corresponding start and end line numbers. Format these fields in an <issue> tag in the following manner:
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

CLAUDE_MODEL = "claude-3-opus-20240229"

@dataclass
class CodeReview:
    file_name: str
    diff_summary: str
    issues: str

class PRReviewBot(ChatGPT):
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
                temperature=0.2,
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
            code_reviews_by_file[file_name] = CodeReview(file_name=file_name, diff_summary=diff_summary, issues=issues)
            if chat_logger:
                chat_logger.add_chat(
                    {
                        "model": self.model,
                        "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                        "output": "END OF MESSAGES",
                    })
        return code_reviews_by_file