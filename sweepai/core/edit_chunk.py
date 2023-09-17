import json
import subprocess
from logn import logger

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.prompts import should_edit_code_system_prompt, should_edit_code_prompt


class EditBot(ChatGPT):
    """
    EditBot is a subclass of ChatGPT that decides whether a given code snippet should be edited.
    """

    def should_edit(self, issue: str, snippet: str) -> bool:
        """
        Determines whether a given code snippet should be edited based on the issue description.

        Parameters:
        issue (str): The issue description.
        snippet (str): The code snippet.

        Returns:
        bool: True if the code snippet should be edited, False otherwise.
        """
        try:
            self.messages = [
                Message(role="system", content=should_edit_code_system_prompt)
            ]
            # self.model = "gpt-3.5-turbo-16k-0613"  # can be optimized
            response = self.chat(
                should_edit_code_prompt.format(
                    problem_description=issue, code_snippet=snippet
                ),
                message_key="is_relevant",
            )
            last_line = response.split("\n")[-1]
            if "true" in last_line.lower():
                return True
            elif "false" in last_line.lower():
                return False
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.print(f"An error occurred: {e}")
        return False
