"""
Take a PR and provide an AI generated review of the PR.
"""
from dataclasses import dataclass
import re
from sweepai.core.chat import ChatGPT
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
class PRChange:
    file_name: str
    diff: str
    old_code: str
    new_code: str
    status: str

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
        pr_diffs.append(PRChange(file_name, diff, old_code, new_code, status))
    return pr_diffs

system_prompt = """You will be analyzing a set of diffs representing a pull request made to a piece of source code. Be very concise."""

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

CLAUDE_MODEL = "claude-3-sonnet-20240229"

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