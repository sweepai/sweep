from src.utils.github_utils import (
    get_relevant_directories,
    get_relevant_directories_remote,
)


def test_query_all():
    relevant_directories, relevant_files = get_relevant_directories(
        "How do I add exponential backoff to OpenAI calls?"
    )
    print(relevant_directories)
    print(relevant_files)


def test_query_jina():
    relevant_directories, relevant_files = get_relevant_directories_remote(
        "How do I add exponential backoff to OpenAI calls?",
        num_files=10,
    )
    print(relevant_directories)
    print(relevant_files)