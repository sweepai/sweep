import logging
import json
import subprocess

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.prompts import should_edit_code_system_prompt, should_edit_code_prompt

class EditBot(ChatGPT):
    def should_edit(self, issue: str, snippet: str) -> bool:
        """
        Determine if a given code snippet should be edited.

        Parameters:
        issue (str): The issue description.
        snippet (str): The code snippet to be evaluated. This is a string of code that may need to be edited based on the issue description.

        Returns:
        bool: True if the code snippet should be edited, False otherwise.
        """
        self.messages = [Message(role="system", content=should_edit_code_system_prompt)]
        self.model = "gpt-3.5-turbo-16k-0613"  # can be optimized
        try:
            response = self.chat(should_edit_code_prompt.format(problem_description=issue, code_snippet=snippet), message_key='is_relevant')
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return False
        last_line = response.split('\n')[-1]
        if "true" in last_line.lower():
            return True
        elif "false" in last_line.lower():
            return False
        return False