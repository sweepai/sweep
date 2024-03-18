import re
from itertools import islice

from github.Repository import Repository
from pydantic import BaseModel

from loguru import logger
from sweepai.config.client import SweepConfig
from sweepai.utils.chat_logger import discord_log_error

summary_format = """# Pull Request #{id_}

## Title: {pr_title}
## Summary:
{pr_summary}

## Here is the diff of the Pull Request:

{diff}
"""

diff_format = """Diffs for file {file_path}:
```diff
{diff}
```
"""


class PRReader(BaseModel):
    repo: Repository

    class Config:
        arbitrary_types_allowed = True

    @staticmethod
    def extract_pr_ids(content: str) -> list[str]:
        pattern_1 = r" #(?P<pr_id>\d+)"
        pattern_2 = (
            r"https://github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+/pull/(?P<pr_id>\d+)"
        )
        return [
            _match.group("pr_id") for _match in set(re.finditer(pattern_1, content))
        ] + [_match.group("pr_id") for _match in set(re.finditer(pattern_2, content))]

    def extract_summary_from_pr_id(self, pr_id: int, sweep_config: SweepConfig = None) -> str:
        pr = self.repo.get_pull(int(pr_id))
        diff = ""
        files = list(islice(pr.get_files(), 51))
        for file in files:
            path = file.filename
            # make sure changes are within allowed directories
            if sweep_config and sweep_config.is_file_excluded(path):
                continue
            patch = file.patch
            diff += diff_format.format(file_path=path, diff=patch)
        return summary_format.format(
            id_=pr_id, pr_title=pr.title, pr_summary=pr.body, diff=diff
        )

    @staticmethod
    def extract_prs(repo: Repository, content: str):
        sweep_config = SweepConfig()
        logger.info("Extracting pull requests from content")
        try:
            pr_reader = PRReader(repo=repo)
            result = ""
            for pr_id in pr_reader.extract_pr_ids(content):
                result += pr_reader.extract_summary_from_pr_id(pr_id, sweep_config = sweep_config)
            if result:
                result = (
                    "The following PRs were mentioned in the issue:\n\n"
                    + result
                    + "\nBe sure to follow the PRs as a reference when making code changes. If the user instructs you to follow the referenced PR, limit the scope of your changes to the referenced PR."
                )
            return result
        except Exception as e:
            logger.error(f"Failed to extract PRs from content: {e}")
            discord_log_error(f"Failed to extract PRs from content: {e}")
            return ""
