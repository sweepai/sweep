from dataclasses import dataclass
from typing import Literal



@dataclass
class GHAFix:
    suite_url: str
    logs: str = ""
    status: Literal["pending"] | Literal["skipped"] | Literal["planning"] | Literal["modifying"] | Literal["done"] = "pending"
    # starts with pending, skip if suite passes
    # if it errors we first plan changes and then mark as done
    fix_commit_hash: str = ""
    fix_diff: str = ""

    @property
    def repo_full_name(self):
        return self.suite_url.split("/")[3:5]

    def to_markdown(self):
        if self.status == "done":
            return f"I resolved the [GitHub Actions errors]({self.suite_url}) at with commit https://github.com/{self.repo_full_name}/commit/{self.fix_commit_hash}. Here were my changes:\n\n{self.fix_diff}"
        elif self.status == "modifying":
            return f"I'm currently resolving the [GitHub Actions errors]({self.suite_url}). Here are my plans:\n\n{self.fix_diff}"
        elif self.status == "planning":
            return f"The GitHub Actions have failed. You can view the logs [here]({self.suite_url}). I'm planning currently trying to fix the errors."
        elif self.status == "skipped":
            return f"The GitHub Actions have completed successfully. You can view the logs [here]({self.suite_url})."
        elif self.status == "pending":
            return "I'm currently waiting for the GitHub Actions to complete running, so that I can address any errors."