import re
from itertools import islice

from github.Repository import Repository
from pydantic import BaseModel

from sweepai.logn import logger

summary_format = """# Pull Request #{id_}

## Title: {pr_title}
## Summary:
{pr_summary}

## Here is the diff of the Pull Request:

{diff}
"""

diff_format = """### Start of diff for file {file_path}
{diff}
### Start of diff for file {file_path}
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

    def extract_summary_from_pr_id(self, pr_id: int) -> str:
        pr = self.repo.get_pull(int(pr_id))
        diff = ""
        files = list(islice(pr.get_files(), 51))
        for file in files:
            path = file.filename
            patch = file.patch
            diff += diff_format.format(file_path=path, diff=patch)
        return summary_format.format(
            id_=pr_id, pr_title=pr.title, pr_summary=pr.body, diff=diff
        )

    @staticmethod
    def extract_prs(repo: Repository, content: str):
        logger.info("Extracting pull requests from content")
        pr_reader = PRReader(repo=repo)
        result = ""
        for pr_id in pr_reader.extract_pr_ids(content):
            result += pr_reader.extract_summary_from_pr_id(pr_id)
        if result:
            result = "The following PRs we're mentioned in the issue:\n\n" + result
        return result
