import subprocess

from sweepai.logn import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.prompts import (
    code_repair_check_prompt,
    code_repair_check_system_prompt,
    code_repair_prompt,
    code_repair_system_prompt,
)

response_regex = r"```[^\n]*(?P<response>.+)```"


class CodeRepairChecker(ChatGPT):
    def check_code(self, diff: str, user_code: str) -> bool:
        self.messages = [
            Message(role="system", content=code_repair_check_system_prompt)
        ]
        self.model = "gpt-4-32k-0613"
        response = self.chat(
            code_repair_check_prompt.format(user_code=user_code),
            message_key="code_repair",
        )
        return "<valid>True</valid>" in response


class CodeRepairer(ChatGPT):
    # idk why this part breaks
    # messages: list[Message] = [Message(role="system", content=code_repair_system_prompt)]
    # model = "gpt-4-32k-0613"
    code_repair_checker: CodeRepairChecker = CodeRepairChecker()

    @staticmethod
    def check_syntax(old_code, file_extension: str) -> bool:
        return False
        # this is WIP
        filename = ""
        if file_extension == ".py":
            # Use Python's built-in formatter "Black"
            result = subprocess.run(
                ["black", "--check", filename], text=True, capture_output=True
            )
        elif file_extension == ".tsx" or file_extension == ".js":
            # Use Prettier for JavaScript and TypeScript formatting
            result = subprocess.run(
                ["prettier", "--check", filename], text=True, capture_output=True
            )
        elif file_extension == ".cs":
            # Use dotnet-format for C# formatting
            result = subprocess.run(
                ["dotnet-format", "--check", "--include", filename],
                text=True,
                capture_output=True,
            )
        elif file_extension == ".go":
            # Use gofmt for Go formatting
            result = subprocess.run(
                ["gofmt", "-l", filename], text=True, capture_output=True
            )
        elif file_extension == ".rs":
            # Use rustfmt for Rust formatting
            result = subprocess.run(
                ["rustfmt", "--check", filename], text=True, capture_output=True
            )
        else:
            logger.print(f"No formatter for {file_extension} files")
            return False

        # If the return code is 0, that means the syntax is correct.
        # Else, there was a syntax error.
        if result.returncode == 0:
            return True
        else:
            logger.print(result.stderr)
            return False

    def repair_code(self, diff: str, user_code: str, feature: str, retries=3) -> str:
        self.messages = [
            Message(
                role="system", content=code_repair_system_prompt.format(feature=feature)
            )
        ]
        self.model = "gpt-4-32k-0613"
        if self.code_repair_checker.check_code(diff, user_code):
            return user_code
        retry_count = 0
        while retry_count < retries:
            response = self.chat(
                code_repair_prompt.format(user_code=user_code),
                message_key="code_repair",
            )
            # Check if the length of the response does not differ by more than 15% from the input
            if (
                len(user_code.splitlines()) > 50
                and abs(len(response.splitlines()) - len(user_code.splitlines()))
                / len(user_code.splitlines())
                > 0.15
            ):
                self.delete_messages_from_chat(key_to_delete="code_repair")
                retry_count += 1
                if retry_count == retries:
                    return user_code
            else:
                break
        return response.strip() + "\n"
