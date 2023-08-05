from loguru import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RewrittenTitleAndDescription
from sweepai.core.prompts import issue_description_rewrite_system_prompt, issue_description_rewrite_prompt, issue_description_rewrite_comments_prompt


class IssueRewriter(ChatGPT):
    def issue_rewrite(self, title: str, description: str, has_comments: bool) -> tuple[str, str]:
        try:
            self.messages = [Message(role="system", content=issue_description_rewrite_system_prompt)]
            self.model = "gpt-4"
            if has_comments:
                response = self.chat(issue_description_rewrite_prompt.format(title=title, description=description))
            else:
                response = self.chat(issue_description_rewrite_comments_prompt.format(title=title, description=description))
            rewritten_title_and_description = RewrittenTitleAndDescription(response)
            issue_title = rewritten_title_and_description.new_title if rewritten_title_and_description.new_title else title
            issue_description = rewritten_title_and_description.new_description if rewritten_title_and_description.new_description else description
            return issue_title, issue_description
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return title, description