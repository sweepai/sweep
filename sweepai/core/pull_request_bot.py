
import re

from loguru import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.diff import generate_diff


commit_message_system_prompt = """Create a concise, informative commit message for GitHub from the code changes.

The output must:
1. Use an imperative tone, such as "Add", "Update", "Remove".
2. Your commit message MUST BE <50 characters long to adhere to GitHub's message length restrictions.
3. Group similar operations where applicable to avoid redundancy.
Your message must be directly related to the file changes stated. Avoid additional interpretation or detail not present in the input.

You will recieve a series of file diffs that need to be described in a short commit message.

Return your commit message in the following xml format:

<thinking>
1. Explain what happened in the file diffs, focusing on the lines added and removed. 
2. Try to identify the ideal commit message that reflects the changes made, whether the changes are substantial or minor. Remember to keep the message concise and clear, focusing on the file operations performed. Again, the commit message must be less than 50 characters long.
</thinking>

<commit_message>
short and concise description of the file diffs for a GitHub commit, not exceeding 50 characters
</commit_message>"""

commit_message_user_prompt = """Below are a series of file diffs to create a github commit message for:

{file_diffs}"""

class PRSummaryBot(ChatGPT):
    # get commit message based on the patches
    # if previous patches are passed in then generate the incremental commit message
    def get_commit_message(
        self, 
        modify_files_dict: dict[str, dict[str, str]], 
        previous_modify_files_dict: dict[str, dict[str, str]] = {},
        chat_logger: ChatLogger = None
    ):
        self.messages = [
            Message(
                role="system",
                content=commit_message_system_prompt,
            )
        ]
        file_diffs = ""
        if not previous_modify_files_dict:
            for file_name, file_data in modify_files_dict.items():
                file_diff = generate_diff(file_data['original_contents'], file_data['contents'])
                file_diffs += f"<file_diffs file='{file_name}'>\n{file_diff}\n</file_diffs>"
        else:
            for file_name, file_data in modify_files_dict.items():
                # use incremental diff, compare against previous file data
                if file_name in previous_modify_files_dict:
                    previous_file_data = previous_modify_files_dict[file_name]
                    file_diff = generate_diff(previous_file_data['contents'], file_data['contents'])
                else:
                    # use diff compare against original file data
                    file_diff = generate_diff(file_data['original_contents'], file_data['contents'])
                file_diffs += f"<file_diffs file='{file_name}'>\n{file_diff}\n</file_diffs>"
            
        formatted_user_prompt = commit_message_user_prompt.format(file_diffs=file_diffs)
        commit_message_response = self.chat_anthropic(
            content=formatted_user_prompt,
            temperature=0.1,
            model="claude-3-haiku-20240307",
        )
        commit_message = self.extract_commit_message(commit_message_response)
        if len(commit_message) > 50:
            shorter_commit_prompt = f'Your commit message is too long and was truncated to "{commit_message[:50]}".\nWrite a shorter commit message than "{commit_message}" that is still coherent.\n<commit_message>'
            shorter_commit_message_response = self.chat_anthropic(
                content=shorter_commit_prompt,
                temperature=0.1,
                model="claude-3-haiku-20240307",
            )
            commit_message = self.extract_commit_message(shorter_commit_message_response)
        if not commit_message:
            logger.error("Failed to extract commit message from response.")
            commit_message = f"feat: Updated {len(modify_files_dict or [])} files"[:50]
        return commit_message
    
    def extract_commit_message(self, response: str):
        commit_message = ""
        commit_message_pattern = r"<commit_message>(?P<commit_message>.*?)</commit_message>"
        commit_message_match = re.search(commit_message_pattern, response, re.DOTALL)
        if commit_message_match:
            commit_message = commit_message_match.group("commit_message").strip()
        return commit_message