import traceback
from collections import OrderedDict

from sweepai.agents.assistant_function_modify import function_modify
from sweepai.core.entities import FileChangeRequest, MaxTokensExceeded, Message
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.diff import generate_diff
from sweepai.utils.event_logger import logger
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo
from sweepai.utils.progress import AssistantConversation, TicketProgress


def is_blocked(file_path: str, blocked_dirs: list[str]):
    for blocked_dir in blocked_dirs:
        if file_path.startswith(blocked_dir) and len(blocked_dir) > 0:
            return {"success": True, "path": blocked_dir}
    return {"success": False}


def create_additional_messages(
    metadata: str,
    file_change_request: FileChangeRequest,
    changed_files: list[tuple[str, str]],
    comment_pr_diff_str: str,
    cloned_repo: ClonedRepo,
):
    additional_messages = [
        Message(
            role="user",
            content=metadata,
            key="issue_metadata",
        )
    ]
    if comment_pr_diff_str and comment_pr_diff_str.strip():
        additional_messages = [
            Message(
                role="user",
                content="These changes have already been made:\n" + comment_pr_diff_str,
                key="pr_diffs",
            )
        ]
    file_path_to_contents = OrderedDict()
    # use only the latest change for each file
    # go forward to find the earliest version of each file in the array
    earliest_version_per_file = {}
    for file_path, (old_contents, new_contents) in changed_files:
        if file_path not in earliest_version_per_file:
            earliest_version_per_file[file_path] = old_contents
    latest_version_per_file = {}
    for file_path, (old_contents, new_contents) in reversed(changed_files):
        if file_path not in latest_version_per_file:
            latest_version_per_file[file_path] = new_contents
    for file_path, _ in changed_files:
        if (
            not latest_version_per_file[file_path]
            or not latest_version_per_file[file_path].strip()
        ):
            continue
        earliest_file_version = earliest_version_per_file[file_path]
        latest_file_version = latest_version_per_file[file_path]
        diffs = generate_diff(earliest_file_version, latest_file_version)
        if file_path not in file_path_to_contents:
            file_path_to_contents[file_path] = diffs
    changed_files_summary = "You have previously changed these files:\n" + "\n".join(
        [
            f'<changed_file file_path="{file_path}">\n{diffs}\n</changed_file>'
            for file_path, diffs in file_path_to_contents.items()
        ]
    )
    if changed_files:
        additional_messages += [
            Message(
                content=changed_files_summary,
                role="user",
                key="changed_files_summary",
            )
        ]
    if file_change_request.relevant_files:
        relevant_files_contents = []
        for file_path in file_change_request.relevant_files:
            try:
                relevant_files_contents.append(cloned_repo.get_file_contents(file_path))
            except Exception:
                for file_path, (old_contents, new_contents) in changed_files:
                    if file_path == file_path:
                        relevant_files_contents.append(new_contents)
                        break
                else:
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
    current_file_diff = ""
    if changed_files:
        for file_path, (old_contents, new_contents) in changed_files:
            if file_path == file_change_request.filename:
                current_file_diff += generate_diff(old_contents, new_contents) + "\n"
    return additional_messages


@file_cache()
def modify_file(
    cloned_repo: ClonedRepo,
    metadata: str,
    file_change_request: FileChangeRequest,
    contents: str = "",
    branch: str = None,
    # context related
    changed_files: list[tuple[str, tuple[str, str]]] = [],
    comment_pr_diff_str: str = "",
    # o11y related
    assistant_conversation: AssistantConversation | None = None,
    ticket_progress: TicketProgress | None = None,
    chat_logger: ChatLogger | None = None,
    additional_messages: list[Message] = [],
):
    new_file = None
    try:
        additional_messages += create_additional_messages(
            metadata,
            file_change_request,
            changed_files,
            comment_pr_diff_str,
            cloned_repo,
        )
        new_file = function_modify(
            file_change_request.instructions,
            file_change_request.filename,
            contents or cloned_repo.get_file_contents(file_change_request.filename),
            additional_messages,
            chat_logger,
            start_line=file_change_request.start_line,
            end_line=file_change_request.end_line,
            ticket_progress=ticket_progress,
            assistant_conversation=assistant_conversation,
        )

    except Exception as e:  # Check for max tokens error
        if "max tokens" in str(e).lower():
            logger.error(f"Max tokens exceeded for {file_change_request.filename}")
            raise MaxTokensExceeded(file_change_request.filename)
        else:
            logger.error(f"Error: {e}")
            logger.error(traceback.format_exc())
            raise e
    return new_file


if __name__ == "__main__":
    cloned_repo = MockClonedRepo("/tmp/sweep", "sweepai/sweep")

    new_file = modify_file(
        cloned_repo=cloned_repo,
        metadata="This repo is Sweep.",
        file_change_request=FileChangeRequest(
            filename="push_image.sh",
            instructions="Add a print hello world statement before running anything.",
            change_type="modify",
        ),
    )
    print(new_file)
