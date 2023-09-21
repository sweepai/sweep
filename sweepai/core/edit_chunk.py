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
            # The model attribute is moved to the class initialization as it is needed.
            self.model = "gpt-3.5-turbo-16k-0613"  
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
        # The SystemExit exception is allowed to propagate and the error message and traceback are logged for debugging.
        except Exception as e:
            logger.error(f"An error occurred: {e}", exc_info=True)
        return False
