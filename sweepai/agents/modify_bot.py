# Necessary imports
import copy
from typing import list, tuple

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, SandboxResponse, ChangeValidation, UnneededEditError, Message
from sweepai.logn import logger
from sweepai.utils.search_and_replace import find_best_match, match_indent, split_ellipses
from sweepai.utils.code_tree import CodeTree
from sweepai.utils.function_call_utils import find_function_calls
from sweepai.agents.complete_code import ExtractLeftoverComments
from sweepai.agents.prune_modify_snippets import PruneModifySnippets
from sweepai.agents.validate_code import ChangeValidator, ChangeValidation
from sweepai.core.sweep_bot import SweepBot

# Define or import the missing variables
fetch_snippets_system_prompt = "Your definition or import here"
update_snippets_system_prompt = "Your definition or import here"

# ModifyBot class definition
class ModifyBot:
    def __init__(
        self,
        additional_messages: list[Message] = [],
        chat_logger=None,
        parent_bot: SweepBot = None,
        is_pr: bool = False,
        **kwargs,
    ):
        self.fetch_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            fetch_snippets_system_prompt, chat_logger=chat_logger, **kwargs
        )
        self.fetch_snippets_bot.messages.extend(additional_messages)
        self.update_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            update_snippets_system_prompt, chat_logger=chat_logger, **kwargs
        )
        self.update_snippets_bot.messages.extend(additional_messages)
        self.parent_bot = parent_bot

        self.extract_leftover_comments_bot: ExtractLeftoverComments = (
            ExtractLeftoverComments(chat_logger=chat_logger, **kwargs)
        )
        self.extract_leftover_comments_bot.messages.extend(additional_messages)
        self.prune_modify_snippets_bot: PruneModifySnippets = (
            PruneModifySnippets(chat_logger=chat_logger, **kwargs)
        )
        self.prune_modify_snippets_bot.messages.extend(additional_messages)
        self.chat_logger = chat_logger
        self.additional_messages = additional_messages

    # Rest of the ModifyBot class methods and properties...
