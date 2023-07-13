from loguru import logger
from pydantic import BaseModel

from sweepai.core.prompts import (
    human_message_prompt,
    human_message_prompt_comment,
    human_message_review_prompt,
    diff_section_prompt,
    review_follow_up_prompt,
    final_review_prompt,
    comment_line_prompt
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
        # super unoptimized
        if file_path in [snippet.file_path for snippet in self.snippets]:
            for snippet in self.snippets:
                if snippet.file_path == file_path:
                    self.snippets.remove(snippet)

    def get_relevant_directories(self):
        deduped_paths = []
        for snippet in self.snippets:
            if snippet.file_path not in deduped_paths:
                deduped_paths.append(snippet.file_path)
        return "\n".join(deduped_paths)

    def render_snippets(self):
        return "\n".join([snippet.xml for snippet in self.snippets])

    def construct_prompt(self):
        human_messages = [{'role': msg['role'], 'content': msg['content'].format(
            repo_name=self.repo_name,
            issue_url=self.issue_url,
            username=self.username,
            repo_description=self.repo_description,
            tree=self.tree,
            title=self.title,
            description=self.summary if self.summary else "No description provided.",
            relevant_snippets=self.render_snippets(),
            relevant_directories=self.get_relevant_directories(),
        ), 'key': msg.get('key')} for msg in human_message_prompt]
        return human_messages


class HumanMessagePromptReview(HumanMessagePrompt):
    pr_title: str
    pr_message: str = ""
    diffs: list

    def format_diffs(self):
        formatted_diffs = []
        for file_name, new_file_contents, old_file_contents, file_patch in self.diffs:
            format_diff = diff_section_prompt.format(
                diff_file_path=file_name,
                new_file_content=new_file_contents.rstrip("\n"),
                previous_file_content=old_file_contents.rstrip("\n"),
                diffs=file_patch
            )
            formatted_diffs.append(format_diff)
        return "\n".join(formatted_diffs)

    def construct_prompt(self):
        human_messages = [{'role': msg['role'], 'content': msg['content'].format(
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
        )} for msg in human_message_review_prompt]

        return human_messages


class HumanMessageReviewFollowup(BaseModel):
    diff: tuple

    def construct_prompt(self):
        file_name, new_file_contents, old_file_contents, file_patch = self.diff
        format_diff = diff_section_prompt.format(
            diff_file_path=file_name,
            new_file_content=new_file_contents.rstrip("\n"),
            previous_file_content=old_file_contents.rstrip("\n"),
            diffs=file_patch
        )
        return review_follow_up_prompt + format_diff


class HumanMessageCommentPrompt(HumanMessagePrompt):
    comment: str
    diffs: list
    pr_file_path: str | None
    pr_line: str | None

    def format_diffs(self):
        formatted_diffs = []
        for file_name, new_file_contents, old_file_contents, file_patch in self.diffs:
            format_diff = diff_section_prompt.format(
                diff_file_path=file_name,
                new_file_content=new_file_contents.rstrip("\n"),
                previous_file_content=old_file_contents.rstrip("\n"),
                diffs=file_patch
            )
            formatted_diffs.append(format_diff)
        return "\n".join(formatted_diffs)

    def construct_prompt(self):
        human_messages = [{'role': msg['role'], 'content': msg['content'].format(
            comment=self.comment,
            repo_name=self.repo_name,
            repo_description=self.repo_description if self.repo_description else "",
            diff=self.format_diffs(),
            issue_url=self.issue_url,
            username=self.username,
            title=self.title,
            tree=self.tree,
            description=self.summary if self.summary else "No description provided.",
            relevant_directories=self.get_relevant_directories(),
            relevant_snippets=self.render_snippets()
        )} for msg in human_message_prompt_comment]

        if self.pr_file_path and self.pr_line:
            logger.info(f"Review Comment {self.comment}")
            human_messages.append({'role': 'user', 'content': comment_line_prompt.format(
                pr_file_path=self.pr_file_path,
                pr_line=self.pr_line
            )})
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
