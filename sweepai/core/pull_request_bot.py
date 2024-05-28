
import re

from loguru import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.diff import generate_diff


commit_message_system_prompt = """[TASK]
Create a concise, imperative commit message for GitHub from file operation descriptions (e.g., added, modified, deleted). The output must:
1. Reflect all relevant file operations clearly.
2. Use an imperative tone, such as "Add", "Update", "Remove".
3. Be under 50 characters to adhere to GitHub's message length restrictions.
4. Group similar operations where applicable, and use plural forms to avoid redundancy.
Examples of operations include adding, modifying, and deleting specific files or sets of files. Keep your messages focused and directly related to the file changes stated, avoiding any additional interpretation or detail not present in the input.

---

[INPUT]
You will recieve a series of file diffs that need to be described.

[OUTPUT]
You are expected to out the the resulting commit message in the following xml format:
<commit_message>
short and concise description of the file diffs for a GitHub commit, not exceeding 50 characters
</commit_message>
"""
commit_message_user_prompt = """[INPUT]
Below are a series of file diffs that you need to create a github commit message for:

{file_diffs}

[OUTPUT]

<commit_message>"""
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
        )
        commit_message = ""
        commit_message_pattern = r"<commit_message>(?P<commit_message>.*?)</commit_message>"
        commit_message_match = re.search(commit_message_pattern, commit_message_response, re.DOTALL)
        if commit_message_match:
            commit_message = commit_message_match.group("commit_message").strip()
        else:
            logger.error("Failed to extract commit message from response.")
            commit_message =f"feat: Updated {len(modify_files_dict or [])} files"[:50]
        if chat_logger:
            chat_logger.add_chat(
                {
                    "model": self.model,
                    "messages": [{"role": message.role, "content": message.content} for message in self.messages],
                    "output": "END OF MESSAGES",
                })
        return commit_message
    