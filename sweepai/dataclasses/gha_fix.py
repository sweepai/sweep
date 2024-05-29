from dataclasses import dataclass
from typing import Literal

from sweepai.core.entities import FileChangeRequest


@dataclass
class GHAFix:
    suite_url: str
    logs: str = ""
    status: Literal["pending"] | Literal["success"] | Literal["failure"] = "pending" # status of suite_url, not the fix
    file_change_requests: list[FileChangeRequest] = []
    fix_commit_hash: str = ""
    fix_diff: str = ""

    @property
    def repo_full_name(self):
        return self.suite_url.split("/")[3:5]

    def to_markdown(
        self,
    ):
        if self.fix_commit_hash:
            # has already been fixed
            return f"I resolved the [GitHub Actions errors]({self.suite_url}) at with commit https://github.com/{self.repo_full_name}/commit/{self.fix_commit_hash}. Here were my changes:\n\n{self.fix_diff}"
        elif self.file_change_requests:
            return f"I'm currently resolving the [GitHub Actions errors]({self.suite_url}). Here are my plans:\n\n{self.fix_diff}"
        else:
            if self.status == "pending":
                return f"I'm currently waiting for the GitHub Actions to complete running, so that I can address any errors."
            elif self.status == "success":
                return f"The GitHub Actions have completed successfully. You can view the logs [here]({self.suite_url})."
            elif self.status == "failed":
                return f"The GitHub Actions have failed. You can view the logs [here]({self.suite_url})."