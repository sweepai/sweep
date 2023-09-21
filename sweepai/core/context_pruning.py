from logn import logger
from sweepai.config.client import get_description
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, ContextToPrune
from sweepai.core.prompts import (
    pruning_prompt,
    system_message_prompt,
    repo_description_prefix_prompt,
)
from sweepai.utils.prompt_constructor import HumanMessagePrompt


class ContextPruning(ChatGPT):
    def prune_context(self, human_message: HumanMessagePrompt, **kwargs) -> list[str]:
        try:
            self.construct_system_message(kwargs)
            self.add_human_messages(human_message)
            self.select_model()
            response = self.chat(pruning_prompt)
            context_to_prune = ContextToPrune.from_string(response)
            return context_to_prune.excluded_snippets, context_to_prune.excluded_dirs
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return [], []
    
    def construct_system_message(self, kwargs):
        content = system_message_prompt
        repo = kwargs.get("repo")
        if repo:
            repo_description = get_description(repo)
            if repo_description:
                content += f"{repo_description_prefix_prompt}\n{repo_description}"
        self.messages = [Message(role="system", content=content, key="system")]
    
    def add_human_messages(self, human_message: HumanMessagePrompt):
        added_messages = human_message.construct_prompt()  # [ { role, content }, ... ]
        for msg in added_messages:
            self.messages.append(Message(**msg))
    
    def select_model(self):
        self.model = (
            "gpt-4-32k"
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else "gpt-3.5-turbo-16k-0613"
        )
