import json
import subprocess

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.prompts import should_edit_code_system_prompt, should_edit_code_prompt

class EditBot(ChatGPT):
    def should_edit(self, issue: str, snippet: str) -> bool:
        """
        Determines if a given code snippet should be edited based on the issue description.

        Parameters:
        issue (str): The issue description.
        snippet (str): The code snippet.

        Returns:
        bool: True if the code snippet should be edited, False otherwise.
        """
        self.messages = [Message(role="system", content=should_edit_code_system_prompt)]
        self.model = "gpt-3.5-turbo-16k-0613"  # can be optimized
        response = self.chat(should_edit_code_prompt.format(problem_description=issue, code_snippet=snippet), message_key='is_relevant')
        return self._should_edit_response(response)

    def _get_last_line(self, response: str) -> str:
        """
        Gets the last line of a response.

        Parameters:
        response (str): The response.

        Returns:
        str: The last line of the response.
        """
        return response.split('\n')[-1]

    def _should_edit_response(self, response: str) -> bool:
        """
        Determines if a response indicates that a code snippet should be edited.

        Parameters:
        response (str): The response.

        Returns:
        bool: True if the response indicates that the code snippet should be edited, False otherwise.
        """
        last_line = self._get_last_line(response)
        if "true" in last_line.lower():
            return True
        elif "false" in last_line.lower():
            return False
        return False