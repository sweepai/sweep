import re

from sweepai.utils.diff import sliding_window_replacement

file_contents = r"""
class ChatGPT(BaseModel):
    messages: list[Message] = [
        Message(
            role="system",
            content=system_message_prompt,
        )
    ]
    prev_message_states: list[list[Message]] = []
    model: ChatModel = (
        "gpt-4-32k-0613" if OPENAI_DO_HAVE_32K_MODEL_ACCESS else "gpt-4-0613"
    )
    chat_logger: ChatLogger | None
    human_message: HumanMessagePrompt | None = None
    file_change_paths: list[str] = []
    sweep_context: SweepContext | None = None
    cloned_repo: ClonedRepo | None = (None,)

    @classmethod
    def from_system_message_content(
        cls,
        human_message: HumanMessagePrompt,
        is_reply: bool = False,
        chat_logger=None,
        sweep_context=None,
        cloned_repo: ClonedRepo | None = None,
        **kwargs,
    ) -> Any:
        content = system_message_prompt
        repo = kwargs.get("repo")
        if repo:
            logger.info(f"Repo: {repo}")
            repo_description = get_description(repo)
            if repo_description:
                logger.info(f"Repo description: {repo_description}")
                content += f"{repo_description_prefix_prompt}\n{repo_description}"
        messages = [Message(role="system", content=content, key="system")]

        added_messages = human_message.construct_prompt()  # [ { role, content }, ... ]
        for msg in added_messages:
            messages.append(Message(**msg))

        return cls(
            messages=messages,
            human_message=human_message,
            chat_logger=chat_logger,
            sweep_context=sweep_context,
            cloned_repo=cloned_repo,
            **kwargs,
        )

    @classmethod
    def from_system_message_string(
        cls, prompt_string, chat_logger: ChatLogger, **kwargs
    ) -> Any:
        return cls(
            messages=[Message(role="system", content=prompt_string, key="system")],
            chat_logger=chat_logger,
            **kwargs,
        )
"""

updated_snippet = r"""
    def from_system_message_content(
        cls,
        human_message: HumanMessagePrompt,
        is_reply: bool = False,
        chat_logger=None,
        sweep_context=None,
        cloned_repo: ClonedRepo | None = None,
        **kwargs,
    ) -> Any:
        content = system_message_prompt
        repo = kwargs.get("repo")
        if repo:
            logger.info(f"Repo: {repo}")
            repo_description = get_description(repo)
            if repo_description:
                logger.info(f"Repo description: {repo_description}")
                content += f"{repo_description_prefix_prompt}\n{repo_description}"
        messages = Messages([Message(role="system", content=content, key="system")])

        added_messages = human_message.construct_prompt()  # [ { role, content }, ... ]
        for msg in added_messages:
            messages.append(Message(**msg))

        return cls(
            messages=messages,
            human_message=human_message,
            chat_logger=chat_logger,
            sweep_context=sweep_context,
            cloned_repo=cloned_repo,
            **kwargs,
        )
""".strip(
    "\n"
)

selected_snippet = r"""
    def from_system_message_content(
        cls,
        human_message: HumanMessagePrompt,
        is_reply: bool = False,
        chat_logger=None,
        sweep_context=None,
        cloned_repo: ClonedRepo | None = None,
        **kwargs,
    ) -> Any:
        content = system_message_prompt
        repo = kwargs.get("repo")
""".strip(
    "\n"
)


def match_indent(generated: str, original: str) -> str:
    indent_type = "\t" if "\t" in original[:5] else " "
    generated_indents = len(generated) - len(generated.lstrip())
    target_indents = len(original) - len(original.lstrip())
    diff_indents = target_indents - generated_indents
    if diff_indents > 0:
        generated = indent_type * diff_indents + generated.replace(
            "\n", "\n" + indent_type * diff_indents
        )
    return generated


def main():
    result = file_contents
    result, _, _ = sliding_window_replacement(
        result.splitlines(),
        selected_snippet.splitlines(),
        updated_snippet.splitlines(),
        match_indent(updated_snippet, selected_snippet).splitlines(),
    )
    result = "\n".join(result)

    ending_newlines = len(file_contents) - len(file_contents.rstrip("\n"))
    result = result.rstrip("\n") + "\n" * ending_newlines
    print(result)


main()
