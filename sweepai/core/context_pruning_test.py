import textwrap

import pytest

from sweepai.core import context_pruning


def test_user_prompt_splitting():
    prompts = ["short prompt", "medium length prompt", "long " * 1000]
    for prompt in prompts:
        messages = context_pruning.split_user_prompt(prompt)
        assert all(len(message) <= context_pruning.MAX_CHARS for message in messages)
        assert prompt == "".join(messages)

def test_query_string():
    query = context_pruning.get_query_string()
    assert "x" * 100000 not in query
