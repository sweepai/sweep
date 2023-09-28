from pydantic import BaseModel

from logn import logger
from sweepai.core.prompts import (
    diff_section_prompt,
    final_review_prompt,
    human_message_prompt,
    human_message_prompt_comment,
    human_message_review_prompt,
    python_human_message_prompt,
)


class HumanMessagePrompt(BaseModel):
    repo_name: str
    issue_url: str
    username: str
    title: str
    summary: str
    snippets: list
    tree: str
    repo_description: str = ""

    def delete_file(self, file_path):
        # Remove the snippets from the main list
        self.snippets = [
            snippet for snippet in self.snippets if snippet.file_path != file_path
        ]

    def get_relevant_directories(self, directory_tag = None):
        deduped_paths = []
        for snippet in self.snippets:
            if snippet.file_path not in deduped_paths:
                deduped_paths.append(snippet.file_path)
        if len(deduped_paths) == 0:
            return ""
        start_directory_tag = "<relevant_paths_in_repo>" if not directory_tag else f"<{directory_tag}>"
        end_directory_tag = "</relevant_paths_in_repo>" if not directory_tag else f"</{directory_tag}>"
        return (
            start_directory_tag
            + "\n"
            + "\n".join(deduped_paths)
            + "\n"
            + end_directory_tag
        )

    def get_file_paths(self):
        return [snippet.file_path for snippet in self.snippets]

    @staticmethod
    def render_snippet_array(snippets, snippet_tag = None):
        joined_snippets = "\n".join([snippet.xml for snippet in snippets])
        start_snippet_tag = "<relevant_snippets_in_repo>" if not snippet_tag else f"<{snippet_tag}>"
        end_snippet_tag = "</relevant_snippets_in_repo>" if not snippet_tag else f"</{snippet_tag}>"
        if joined_snippets.strip() == "":
            return ""
        return (
            start_snippet_tag
            + "\n"
            + joined_snippets
            + "\n"
            + end_snippet_tag
        )

    def render_snippets(self):
        return self.render_snippet_array(self.snippets)

    def construct_prompt(self, snippet_tag = None, directory_tag = None):
        human_messages = [
            {
                "role": msg["role"],
                "content": msg["content"].format(
                    repo_name=self.repo_name,
                    issue_url=self.issue_url,
                    username=self.username,
                    repo_description=self.repo_description,
                    tree=self.tree,
                    title=self.title,
                    description=self.summary
                    if self.summary
                    else "No description provided.",
                    relevant_snippets=self.render_snippet_array(self.snippets, snippet_tag),
                    relevant_directories=self.get_relevant_directories(directory_tag),
                ),
                "key": msg.get("key"),
            }
            for msg in human_message_prompt
        ]
        return human_messages

    def get_issue_metadata(self):
        return f"""# Repo & Issue Metadata
Repo: {self.repo_name}: {self.repo_description}
Issue: {self.issue_url}
Username: {self.username}
Issue Title: {self.title}
Issue Description: {self.summary}
"""


class PythonHumanMessagePrompt(HumanMessagePrompt):
    def construct_prompt(self):
        human_messages = [
            {
                "role": msg["role"],
                "content": msg["content"].format(
                    repo_name=self.repo_name,
                    issue_url=self.issue_url,
                    username=self.username,
                    repo_description=self.repo_description,
                    tree=self.tree,
                    title=self.title,
                    description=self.summary
                    if self.summary
                    else "No description provided.",
                    relevant_snippets=self.render_snippets(),
                    relevant_directories=self.get_relevant_directories(),
                ),
                "key": msg.get("key"),
            }
            for msg in python_human_message_prompt
        ]
        return human_messages

    def render_snippets(self):
        res = ""
        for snippet in self.snippets:
            snippet_text = (
                f"<snippet source={snippet.file_path}>\n{snippet.content}\n</snippet>\n"
            )
            res += snippet_text
        return res


class HumanMessagePromptReview(HumanMessagePrompt):
    pr_title: str
    pr_message: str = ""
    diffs: list
    plan: str

    def format_diffs(self):
        formatted_diffs = []
        for file_name, file_patch in self.diffs:
            if not file_name and not file_patch:
                continue
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
                    repo_name=self.repo_name,
                    issue_url=self.issue_url,
                    username=self.username,
                    repo_description=self.repo_description,
                    tree=self.tree,
                    title=self.title,
                    description=self.summary,
                    relevant_snippets=self.render_snippets(),
                    relevant_directories=self.get_relevant_directories(),
                    diffs=self.format_diffs(),
                    pr_title=self.pr_title,
                    pr_message=self.pr_message,
                    plan=self.plan,
                ),
            }
            for msg in human_message_review_prompt
        ]

        return human_messages


class HumanMessageCommentPrompt(HumanMessagePrompt):
    comment: str
    diffs: list
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
                    repo_description=self.repo_description
                    if self.repo_description
                    else "",
                    diff=self.format_diffs(),
                    issue_url=self.issue_url,
                    username=self.username,
                    title=self.title,
                    tree=self.tree,
                    description=self.summary
                    if self.summary
                    else "No description provided.",
                    relevant_directories=self.get_relevant_directories(),
                    relevant_snippets=self.render_snippets(),
                ),
            }
            for msg in human_message_prompt_comment
        ]

        if self.pr_file_path and self.pr_chunk and self.original_line:
            logger.info(f"Review Comment {self.comment}")
        else:
            logger.info(f"General Comment {self.comment}")

        return human_messages


class HumanMessageFinalPRComment(BaseModel):
    summarization_replies: list

    def construct_prompt(self):
        final_review = final_review_prompt.format(
            file_summaries="\n".join(self.summarization_replies)
        )
        return final_review
