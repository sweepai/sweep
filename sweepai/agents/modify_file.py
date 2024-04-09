import traceback

from sweepai.agents.assistant_function_modify import function_modify
from sweepai.core.entities import FileChangeRequest, Message
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
    file_change_requests: list[FileChangeRequest],
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
        additional_messages += [
            Message(
                role="user",
                content="These changes have already been made:\n" + comment_pr_diff_str,
                key="pr_diffs",
            )
        ]
    for file_change_request in file_change_requests:
        if file_change_request.relevant_files:
            # keep all relevant_filepaths
            for file_path in file_change_request.relevant_files:
                relevant_filepaths.append(file_path)
    return additional_messages, relevant_filepaths


@file_cache()
def modify_file(
    cloned_repo: ClonedRepo,
    request: str,
    metadata: str,
    file_change_requests: list[FileChangeRequest],
    branch: str = None,
    comment_pr_diff_str: str = "",
    # o11y related
    assistant_conversation: AssistantConversation | None = None,
    ticket_progress: TicketProgress | None = None,
    chat_logger: ChatLogger | None = None,
    additional_messages: list[Message] = [],
    previous_modify_files_dict: dict[str, dict[str, str]] = None,
):
    try:
        new_additional_messages, relevant_filepaths = create_additional_messages(
            metadata,
            file_change_requests,
            comment_pr_diff_str,
            cloned_repo,
        )
        additional_messages += new_additional_messages
        new_files, _ = function_modify(
            file_change_requests,
            request,
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
            file_change_requests=[FileChangeRequest(
                filename="sweepai/api.py",
                instructions="import math at the top of the file",
                change_type="modify",
            )],
        )
        print(new_file)
    except Exception as e:
        logger.error(f"modify_file.py failed to run successfully with error: {e}")
        raise e
