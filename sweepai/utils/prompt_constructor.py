from pydantic import BaseModel

from sweepai.core.prompts import (
    diff_section_prompt,
    final_review_prompt,
    human_message_prompt,
    human_message_prompt_comment,
)

def get_issue_request(
    title: str,
    summary: str
):
    summary = (
        summary if not summary.strip().endswith("_No response_") else ""
    )
    return f"""Issue Title: {title}"""

class HumanMessagePrompt(BaseModel):
    repo_name: str
    title: str
    summary: str
    snippets: list
    tree: str
    repo_description: str = ""
    snippet_text: str = ""
    commit_history: list = []

    def delete_file(self, file_path):
        # Remove the snippets from the main list
        self.snippets = [
            snippet for snippet in self.snippets if snippet.file_path != file_path
        ]

    def get_relevant_directories(self, directory_tag=None):
        deduped_paths = []
        for snippet in self.snippets:
            if snippet.file_path not in deduped_paths:
                deduped_paths.append(snippet.file_path)
        if len(deduped_paths) == 0:
            return ""
        start_directory_tag = (
            "<relevant_paths_in_repo>" if not directory_tag else f"<{directory_tag}>"
        )
        end_directory_tag = (
            "</relevant_paths_in_repo>" if not directory_tag else f"</{directory_tag}>"
        )
        return (
            start_directory_tag
            + "\n"
            + "\n".join(deduped_paths)
            + "\n"
            + end_directory_tag
        )

    def get_commit_history(self, commit_tag=None):
        return ""
        if len(self.commit_history) == 0:
            return ""
        start_commit_tag = (
            "<relevant_commit_history>" if not commit_tag else f"<{commit_tag}>"
        )
        end_commit_tag = (
            "</relevant_commit_history>" if not commit_tag else f"</{commit_tag}>"
        )
        return (
            start_commit_tag
            + "\n"
            + "\n".join(self.commit_history)
            + "\n"
            + end_commit_tag
        )

    def get_file_paths(self):
        return [snippet.file_path for snippet in self.snippets]

    @staticmethod
    def render_snippet_array(snippets, snippet_tag=None):
        joined_snippets = "\n".join(
            [snippet.get_xml(add_lines=False) for snippet in snippets]
        )
        start_snippet_tag = (
            "<relevant_snippets_in_repo>" if not snippet_tag else f"<{snippet_tag}>"
        )
        end_snippet_tag = (
            "</relevant_snippets_in_repo>" if not snippet_tag else f"</{snippet_tag}>"
        )
        if joined_snippets.strip() == "":
            return ""
        return start_snippet_tag + "\n" + joined_snippets + "\n" + end_snippet_tag

    def render_snippets(self):
        return self.render_snippet_array(self.snippets)

    def construct_prompt(self, snippet_tag=None, directory_tag=None, commit_tag=None):
        relevant_snippets = (
            self.snippet_text
            if self.snippet_text
            else self.render_snippet_array(self.snippets, snippet_tag)
        )
        relevant_directories = (
            self.get_relevant_directories(directory_tag)
            if self.get_relevant_directories(directory_tag)
            else ""
        )
        relevant_commit_history = self.get_commit_history(commit_tag)
        human_messages = [
            {
                "role": msg["role"],
                "content": msg["content"].format(
                    repo_name=self.repo_name,
                    repo_description=self.repo_description,
                    tree=self.tree.strip("\n"),
                    title=self.title,
                    description=(
                        f"Issue Description: {self.summary}"
                        if self.summary.strip()
                        else ""
                    ),
                    relevant_snippets=relevant_snippets,
                    relevant_directories=relevant_directories,
                    relevant_commit_history=relevant_commit_history,
                ),
                "key": msg.get("key"),
            }
            for msg in human_message_prompt
        ]
        return human_messages

    def get_issue_metadata(self):
        self.summary = (
            self.summary if not self.summary.strip().endswith("_No response_") else ""
        )
        issue_description = (
            f"\nIssue Description: {self.summary}" if self.summary else ""
        )
        return f"""# Repo & Issue Metadata
Repo: {self.repo_name}: {self.repo_description}
Issue Title: {self.title}
{issue_description}"""
    
    def get_issue_request(self):
        self.summary = (
            self.summary if not self.summary.strip().endswith("_No response_") else ""
        )
        issue_description = (
            f"\nIssue Description: {self.summary}" if self.summary else ""
        )
        return f"""Issue Title: {self.title}
{issue_description}"""


def render_snippets(snippets):
    res = ""
    for snippet in snippets:
        snippet_text = (
            f"<snippet source={snippet.file_path}>\n{snippet.content}\n</snippet>\n"
        )
        res += snippet_text
    return res

class HumanMessageCommentPrompt(HumanMessagePrompt):
    comment: str
    diffs: list
    relevant_docs: str | None
    pr_file_path: str | None
    pr_chunk: str | None
    original_line: str | None

    def format_diffs(self):
        formatted_diffs = []
        for file_name, file_patch in self.diffs:
            format_diff = diff_section_prompt.format(
                diff_file_path=file_name, diffs=file_patch
            )
            formatted_diffs.append(format_diff)
        return "\n".join(formatted_diffs)

    def construct_prompt(self):
        human_messages = [
            {
                "role": msg["role"],
                "content": msg["content"].format(
                    comment=(
                        self.comment[len("sweep:") :].strip()
                        if self.comment.startswith("sweep:")
                        else self.comment
                    ),
                    repo_name=self.repo_name,
                    repo_description=(
                        self.repo_description if self.repo_description else ""
                    ),
                    diff=self.format_diffs(),
                    title=self.title,
                    tree=self.tree,
                    description=self.summary if self.summary.strip() else "",
                    relevant_directories=self.get_relevant_directories(),
                    relevant_snippets=self.render_snippets(),
                    relevant_commit_history=self.get_commit_history(),
                    relevant_docs=(
                        f"\n{self.relevant_docs}" if self.relevant_docs else ""
                    ),  # conditionally add newline
                ),
            }
            for msg in human_message_prompt_comment
        ]
        return human_messages

    def get_issue_metadata(self):
        self.summary = (
            self.summary if not self.summary.strip().endswith("_No response_") else ""
        )
        issue_description = (
            f"\nIssue Description: {self.summary}" if self.summary.strip() else ""
        )
        return f"""# Repo & Issue Metadata
Repo: {self.repo_name}: {self.repo_description}
Issue Title: {self.title}
{issue_description}
The above was the original plan. Please address the user comment: {self.comment}"""


class HumanMessageFinalPRComment(BaseModel):
    summarization_replies: list

    def construct_prompt(self):
        final_review = final_review_prompt.format(
            file_summaries="\n".join(self.summarization_replies)
        )
        return final_review
