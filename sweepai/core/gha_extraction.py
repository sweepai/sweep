from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel
from sweepai.logn import logger

gha_extraction_system_prompt = """\
You are a brilliant engineer who is helping their coworker debug a failing run. Extract the relevant lines from the failing Github Actions logs for debugging.

Format your response as follows:
<extracted_lines>
{copied important lines from the failing github action}
</extracted_lines>

<command>
{command that failed}
</command>
"""

gha_extraction_prompt = """\
Here are the logs:
{gha_logs}

Copy the lines from the logs corresponding to the error. Mention the command that failed.
"""


class ExtractLines(RegexMatchableBaseModel):
    _regex = r"""extracted_lines>(\n)?(?P<extracted_lines>[\s\S]*?)</extracted_lines"""
    extracted_lines: str
    failing_command: str


class GHAExtractor(ChatGPT):
    def gha_extract(self, gha_logs: str) -> str:
        try:
            self.messages = [
                Message(role="system", content=gha_extraction_system_prompt)
            ]
            self.model = "gpt-3.5-turbo-16k-0613"  # can be optimized
            logger.print(gha_logs)
            response = self.chat(gha_extraction_prompt.format(gha_logs=gha_logs))
            extracted_lines = ExtractLines.from_string(response).extracted_lines.strip()
            return f"```{extracted_lines}```\n"
        except Exception as e:
            logger.error(e)
            return ""
