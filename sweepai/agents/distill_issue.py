import re
from github import Github

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message

system_prompt = """Your job is to clean up a GitHub issue for a contract developer to resolve.

Respond in the following format:

<distilled_issue>
```
Sections of the markdown file copied verbose.
```
</distilled_issue>"""

user_prompt = """First, concisely summarize what the GitHub issue is asking us to solve. Then, give me all the markdown blocks in this GitHub issue with crucial pieces of information for solving the issue.

Things to keep:
- The original problem.
- The root cause.
- The fix.
- Additional crucial details for solving the issue.
- Copy all the links to one area at the end, such as backlinks to issues, references to files and PRs.

Things to remove:
- The summary, unless it contains crucial details.
- The suggested implementation.

I will pass these details to a contract developer to resolve the issue so make sure it is concise and complete. Ignore the summary and ignore areas with excessive implementation detail.

Respond in the following format:

<distilled_issue>
```
Sections of the markdown file copied verbose.
```
</distilled_issue>"""

issue_suffix = "\n\n**The recommended fixes may not be complete. There may be missing details such as relevant files or additional steps required to resolve the issue.**\n\n<!-- DISTILLED_SUMMARY -->"
DISTILLED_SUMMARY_MARKER = "<!-- DISTILLED_SUMMARY -->"

def distill_issue(text: str):
    if DISTILLED_SUMMARY_MARKER in text:
        return text
    chatgpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=system_prompt
            ),
            Message(
                role="user",
                content=text
            ),
        ]
    )
    response = chatgpt.chat(user_prompt)
    pattern = r"<distilled_issue>\n```\n(.*?)\n```\n</distilled_issue>"
    matches = re.search(pattern, response, re.DOTALL)
    if not matches:
        return text + issue_suffix
    distilled_text = matches.group(1)
    return distilled_text + issue_suffix

if __name__ == "__main__":
    import os
    issue_url = "https://github.com/sweepai/e2e/issues/32"

    *_, org_name, repo_name, _, issue_number = issue_url.split("/")
    g = Github(os.environ.get("GITHUB_PAT"))
    repo = g.get_repo(f"{org_name}/{repo_name}")
    issue = repo.get_issue(int(issue_number))

    print(distill_issue(issue.body))
