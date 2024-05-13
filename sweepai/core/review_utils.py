"""
Take a PR and provide an AI generated review of the PR.
"""
from dataclasses import dataclass
import re
from sweepai.core.chat import ChatGPT
from sweepai.core.review_annotations import get_diff_annotations
from sweepai.core.sweep_bot import safe_decode
from sweepai.logn.cache import file_cache
from sweepai.utils.event_logger import logger
from github.Repository import Repository
from github.PullRequest import PullRequest

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
    for file in file_diffs:
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
            changes = hunk[hunk.index('@@')+2:].strip()
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
<pr_change index="{idx}">
<file_patches>
{patches}
</file_patches>
<source>
{file_contents}
</source>
</pr_change>"""

patch_format = """\
<patch file_name="{file_name}" index="{index}">
{diff}
</patch>
<patch_annotation file_name="{file_name}" index="{index}">
{annotation}
</patch_annotation>"""

def format_pr_change(pr_change: PRChange, idx: int=0):
    patches = ""
    for idx, patch in enumerate(pr_change.patches):
        patches += "\n" + patch_format.format(
            file_name=pr_change.file_name,
            index=idx,
            diff=patch.changes,
            annotation=pr_change.annotations[idx]
        )
    return pr_change_unformatted.format(
        idx=idx,
        patches=patches,
        file_contents=pr_change.new_code
    )

def format_pr_changes(pr_changes: list[PRChange]):
    formatted_pr_changes = pr_changes_prefix
    for idx, pr_change in enumerate(pr_changes):
        formatted_pr_changes += format_pr_change(pr_change, idx)
    return formatted_pr_changes

system_prompt = """You are a careful and smart tech lead that wants to avoid production issues. You will be analyzing a set of diffs representing a pull request made to a piece of source code. Be very concise."""

user_prompt = """\
# Code Review
Here are the changes in the pull request diffs:
<diffs>
{diff}
</diffs>

And here is the full source code after applying the pull request changes:
<source_code>
{new_code}
</source_code>

# Instructions
1. Analyze the code changes.
    1a. Describe the key changes that were made in the diffs. (1 paragraph)
    1b. Format your response using the following XML tags. Each summary should be a single sentence and formatted within a <diff_summary> tag.:
<diff_summaries>
<diff_summary>
{{Summary of changes}}
</diff_summary>
...
</diff_summaries>

2. Identify all issues.
    2a. Determine whether there are any functional issues, bugs, edge cases, or error conditions that the code changes introduce or fail to properly handle. (1 paragraph)
    2b. Determine whether there are any security vulnerabilities or potential security issues introduced by the code changes. (1 paragraph)
    2c. Identify any other potential issues that the code changes may introduce that were not captured by 2a or 2b. (1 paragraph)
    2d. Format the found issues and root causes using the following XML tags. Each issue should be a single sentence and formatted within an <issue> tag:
<issues>
<issue>
{{Issue 1}}
</issue>
...
</issues>

Focus your analysis solely on potential functional issues with the code changes. Do not comment on stylistic, formatting, or other more subjective aspects of the code."""

CLAUDE_MODEL = "claude-3-opus-20240229"

@dataclass
class CodeReview:
    diff_summary: str
    issues: str

class PRReviewBot(ChatGPT):
    def review_code_changes(self, pr_changes: list[PRChange]):
        self.messages = []
        formatted_user_prompt = user_prompt.format(
            diff="\n".join([change.diff for change in pr_changes]),
            new_code="\n".join([change.new_code for change in pr_changes]),
        )
        code_review_response = self.chat_anthropic(
            content=formatted_user_prompt,
            temperature=0.2,
            model=CLAUDE_MODEL,
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
        code_review = CodeReview(diff_summary=diff_summary, issues=issues)
        return code_review