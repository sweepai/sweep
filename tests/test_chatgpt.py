from loguru import logger
import openai
<<<<<<< HEAD
from src.core.chat import ChatGPT, Message
from src.utils.prompt_constructor import HumanMessagePrompt
from src.core.prompts import system_message_prompt, reply_prompt
=======
from sweepai.core.chat import (
    ChatGPT,
    Message
)
from sweepai.utils.prompt_constructor import (
    HumanMessagePrompt
)
from sweepai.core.prompts import (
    system_message_prompt,
    reply_prompt
)
>>>>>>> main

expected_original_messages = [
    {
        "role": "system",
        "content": 'You\'re name is Sweep bot. You are an engineer assigned to the following Github ticket. You will be helpful and friendly, but informal and concise: get to the point. You will use Github-style markdown when needed to structure your responses.\n\n\nRepo: sweepai/sweep-test: test_repo_description\nIssue: test_issue\nUsername: test_user\nTitle: test_title\nDescription: test_summary\n\nRelevant Directories:\n<relevant_directories>\ntest_file_path_a\ntest_file_path_b\n</relevant_directories>\n\nRelevant Files:\n<relevant_files>\n```\ntest_file_path_a\n"""\ntest_file_contents_a\n"""\ntest_file_path_b\n"""\ntest_file_contents_b\n"""\n```\n</relevant_files>\n',
    }
]

expected_deletion_messages = [
    {
        "role": "system",
        "content": 'You\'re name is Sweep bot. You are an engineer assigned to the following Github ticket. You will be helpful and friendly, but informal and concise: get to the point. You will use Github-style markdown when needed to structure your responses.\n\n\nRepo: sweepai/sweep-test: test_repo_description\nIssue: test_issue\nUsername: test_user\nTitle: test_title\nDescription: test_summary\n\nRelevant Directories:\n<relevant_directories>\ntest_file_path_a\n</relevant_directories>\n\nRelevant Files:\n<relevant_files>\n```\ntest_file_path_a\n"""\ntest_file_contents_a\n"""\n```\n</relevant_files>\n',
    }
]

example_file_prompt = "modify test_file_contents_a"
example_file_contents_file_a = "test_file_contents_a was modified"
example_file_summary_file_a = "test_file_contents_a modified"


def run_tests_for_deletion():
    repo_name = "sweepai/sweep-test"
    issue_url = "test_issue"
    username = "test_user"
    repo_description = "test_repo_description"
    title = "test_title"
    summary = "test_summary"
    file_path_to_contents = {
        "test_file_path_a": "test_file_contents_a",
        "test_file_path_b": "test_file_contents_b",
    }
    human_message = HumanMessagePrompt(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        summary=summary,
        file_path_to_contents=file_path_to_contents,
    )
    bot = ChatGPT.from_system_message_content(
        human_message=human_message, model="gpt-4"
    )
    if bot.messages_dicts == expected_original_messages:
        logger.info("Test passed!")
    else:
        logger.info("Test failed!")
        logger.info(f"Constructed messages: {bot.messages_dicts}")
        logger.info(f"Expected messages: {expected_original_messages}")
    bot.delete_file_from_system_message("test_file_path_b")
    if bot.messages_dicts == expected_deletion_messages:
        logger.info("Test passed!")
    else:
        logger.info("Test failed!")
        logger.info(f"Constructed messages: {bot.messages_dicts}")
        logger.info(f"Expected messages: {expected_deletion_messages}")
    bot.delete_messages_from_chat(message_key="system")
    if bot.messages_dicts == []:
        logger.info("Test passed!")
    else:
        logger.info("Test failed!")
        logger.info(f"Constructed messages: {bot.messages_dicts}")
        logger.info(f"Expected messages: []")


def run_tests_for_summarization():
    repo_name = "sweepai/sweep-test"
    issue_url = "test_issue"
    username = "test_user"
    repo_description = "test_repo_description"
    title = "test_title"
    summary = "test_summary"
    file_path_to_contents = {
        "test_file_path_a": "test_file_contents_a",
        "test_file_path_b": "test_file_contents_b",
    }
    human_message = HumanMessagePrompt(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        summary=summary,
        file_path_to_contents=file_path_to_contents,
    )
    bot = ChatGPT.from_system_message_content(
        human_message=human_message, model="gpt-4"
    )
    bot.messages.append(
        Message(role="user", content=example_file_prompt, key="file_change_test_file_a")
    )
    bot.messages.append(
        Message(
            role="assistant",
            content=example_file_contents_file_a,
            key="file_change_test_file_a",
        )
    )
    insert_summary = "test_file_contents_a modified"
    bot.summarize_message(
        message_key="file_change_test_file_a",
        summarized_content=example_file_summary_file_a,
        user_summary=insert_summary,
    )
    bot_user_summary_message = bot.get_message_content_from_message_key(
        "file_change_test_file_a", message_role="user"
    )
    bot_assistant_summary_message = bot.get_message_content_from_message_key(
        "file_change_test_file_a", message_role="assistant"
    )
    if bot_assistant_summary_message != example_file_summary_file_a:
        logger.info("Test failed!")
        logger.info(f"Constructed messages: {bot_assistant_summary_message}")
        logger.info(f"Expected messages: {example_file_summary_file_a}")
    elif bot_user_summary_message != insert_summary:
        logger.info("Test failed!")
        logger.info(f"Constructed messages: {bot_user_summary_message}")
        logger.info(f"Expected messages: {insert_summary}")
    else:
        logger.info("Test passed!")


if __name__ == "__main__":
    # run_tests_for_deletion()
    run_tests_for_summarization()
