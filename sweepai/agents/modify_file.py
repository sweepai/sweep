import traceback

from sweepai.agents.agent_utils import ensure_additional_messages_length
from sweepai.agents.assistant_function_modify import function_modify
from sweepai.core.entities import FileChangeRequest, MaxTokensExceeded, Message
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import logger
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.progress import AssistantConversation, TicketProgress


def is_blocked(file_path: str, blocked_dirs: list[str]):
    for blocked_dir in blocked_dirs:
        if file_path.startswith(blocked_dir) and len(blocked_dir) > 0:
            return {"success": True, "path": blocked_dir}
    return {"success": False}


def create_additional_messages(
    metadata: str,
    file_change_request: FileChangeRequest,
    comment_pr_diff_str: str,
    cloned_repo: ClonedRepo,
) -> tuple[list[Message], list[str]]:
    additional_messages = [
        Message(
            role="user",
            content=metadata,
            key="issue_metadata",
        )
    ]
    relevant_filepaths = []
    if comment_pr_diff_str and comment_pr_diff_str.strip():
        additional_messages = [
            Message(
                role="user",
                content="These changes have already been made:\n" + comment_pr_diff_str,
                key="pr_diffs",
            )
        ]
    # use only the latest change for each file
    # go forward to find the earliest version of each file in the array

    if file_change_request.relevant_files:
        relevant_files_contents = []
        for file_path in file_change_request.relevant_files:
            try:
                relevant_files_contents.append(cloned_repo.get_file_contents(file_path))
            except Exception:
                relevant_files_contents.append("File not found")
        if relevant_files_contents:
            relevant_files_summary = "Relevant files in this PR:\n\n" + "\n".join(
                [
                    f'<relevant_file file_path="{file_path}">\n{file_contents}\n</relevant_file>'
                    for file_path, file_contents in zip(
                        file_change_request.relevant_files,
                        relevant_files_contents,
                    )
                ]
            )
            additional_messages.append(
                Message(
                    content=relevant_files_summary,
                    role="user",
                    key="relevant_files_summary",
                )
            )
            # keep all relevant_filepaths
            for file_path in file_change_request.relevant_files:
                relevant_filepaths.append(file_path)
    return additional_messages, relevant_filepaths


@file_cache()
def modify_file(
    cloned_repo: ClonedRepo,
    metadata: str,
    file_change_request: FileChangeRequest,
    contents: str = "",
    branch: str = None,
    comment_pr_diff_str: str = "",
    # o11y related
    assistant_conversation: AssistantConversation | None = None,
    ticket_progress: TicketProgress | None = None,
    chat_logger: ChatLogger | None = None,
    additional_messages: list[Message] = [],
    previous_modify_files_dict: dict[str, dict[str, str | list[str]]] = None,
):
    try:
        relevant_file_messages, relevant_filepaths = create_additional_messages(
            metadata,
            file_change_request,
            comment_pr_diff_str,
            cloned_repo,
        )
        additional_messages += relevant_file_messages
        additional_messages = ensure_additional_messages_length(additional_messages)
        new_files = function_modify(
            file_change_request.instructions,
            file_change_request.filename,
            contents or cloned_repo.get_file_contents(file_change_request.filename),
            cloned_repo,
            additional_messages,
            chat_logger,
            ticket_progress=ticket_progress,
            assistant_conversation=assistant_conversation,
            relevant_filepaths=relevant_filepaths,
            cwd=cloned_repo.repo_dir,
            previous_modify_files_dict=previous_modify_files_dict,
        )

    except Exception as e:  # Check for max tokens error
        if "max tokens" in str(e).lower():
            logger.error(f"Max tokens exceeded for {file_change_request.filename}")
            raise MaxTokensExceeded(file_change_request.filename)
        else:
            logger.error(f"Error: {e}")
            logger.error(traceback.format_exc())
            raise e
    return new_files


if __name__ == "__main__":
    try:
        from sweepai.utils.github_utils import get_installation_id
        organization_name = "sweepai"
        installation_id = get_installation_id(organization_name)
        cloned_repo = ClonedRepo("sweepai/sweep", installation_id, "main")

        new_file = modify_file(
            cloned_repo=cloned_repo,
            metadata="This repo is Sweep.",
            file_change_request=FileChangeRequest(
                filename="sweepai/api.py",
                instructions="import math at the top of the file",
                change_type="modify",
            ),
        )
        print(new_file)
    except Exception as e:
        logger.error(f"modify_file.py failed to run successfully with error: {e}")
        raise e
