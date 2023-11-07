import subprocess

from sweepai.config.server import DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.prompts import (
    code_repair_check_prompt,
    code_repair_check_system_prompt,
    code_repair_prompt,
    code_repair_system_prompt,
)
from sweepai.logn import logger

response_regex = r"```[^\n]*(?P<response>.+)```"


class CodeRepairChecker(ChatGPT):
    def check_code(self, diff: str, user_code: str) -> bool:
        self.messages = [
            Message(role="system", content=code_repair_check_system_prompt)
        ]
        self.model = DEFAULT_GPT35_MODEL
        response = self.chat(
            code_repair_check_prompt.format(user_code=user_code),
            message_key="code_repair",
        )
        return "<valid>True</valid>" in response


class CodeRepairer(ChatGPT):
    code_repair_checker: CodeRepairChecker = CodeRepairChecker()

    @staticmethod
    def check_syntax(old_code, file_extension: str) -> bool:
        return False
        filename = ""
        if file_extension == ".py":
            result = subprocess.run(
                ["black", "--check", filename], text=True, capture_output=True
            )
        elif file_extension == ".tsx" or file_extension == ".js":
            result = subprocess.run(
                ["prettier", "--check", filename], text=True, capture_output=True
            )
        elif file_extension == ".cs":
            result = subprocess.run(
                ["dotnet-format", "--check", "--include", filename],
                text=True,
                capture_output=True,
            )
        elif file_extension == ".go":
            result = subprocess.run(
                ["gofmt", "-l", filename], text=True, capture_output=True
            )
        elif file_extension == ".rs":
            result = subprocess.run(
                ["rustfmt", "--check", filename], text=True, capture_output=True
            )
        else:
            logger.print(f"No formatter for {file_extension} files")
            return False
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
        self.model = DEFAULT_GPT35_MODEL
        if self.code_repair_checker.check_code(diff, user_code):
            return user_code
        retry_count = 0
        while retry_count < retries:
            response = self.chat(
                code_repair_prompt.format(user_code=user_code),
                message_key="code_repair",
            )
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
