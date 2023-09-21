from logn import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.prompts import gha_extraction_system_prompt, gha_extraction_prompt


class GHAExtractor(ChatGPT):
    def gha_extract(self, gha_logs: str, model_name: str = "gpt-3.5-turbo-16k-0613") -> str:
        self.messages = [Message(role="system", content=gha_extraction_system_prompt)]
        self.model = model_name
        response = self.chat(gha_extraction_prompt.format(gha_logs=gha_logs))
        self.undo()
        return response.strip() + "\n"
