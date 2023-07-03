from loguru import logger
import openai
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
import unittest

expected_original_messages = [{'role': 'system', 
'content': 'You\'re name is Sweep bot. You are an engineer assigned to the following Github ticket. You will be helpful and friendly, but informal and concise: get to the point. You will use Github-style markdown when needed to structure your responses.\n\n\nRepo: sweepai/sweep-test: test_repo_description\nIssue: test_issue\nUsername: test_user\nTitle: test_title\nDescription: test_summary\n\nRelevant Directories:\n<relevant_directories>\ntest_file_path_a\ntest_file_path_b\n</relevant_directories>\n\nRelevant Files:\n<relevant_files>\n```\ntest_file_path_a\n'''\ntest_file_contents_a\n'''\ntest_file_path_b\n'''\ntest_file_contents_b\n'''\n```\n</relevant_files>\n'}]

expected_deletion_messages = [{'role': 'system', 
'content': 'You\'re name is Sweep bot. You are an engineer assigned to the following Github ticket. You will be helpful and friendly, but informal and concise: get to the point. You will use Github-style markdown when needed to structure your responses.\n\n\nRepo: sweepai/sweep-test: test_repo_description\nIssue: test_issue\nUsername: test_user\nTitle: test_title\nDescription: test_summary\n\nRelevant Directories:\n<relevant_directories>\ntest_file_path_a\n</relevant_directories>\n\nRelevant Files:\n<relevant_files>\n```\ntest_file_path_a\n'''\ntest_file_contents_a\n'''\n```\n</relevant_files>\n'}]

example_file_prompt = "modify test_file_contents_a"
example_file_contents_file_a = "test_file_contents_a was modified"
example_file_summary_file_a = "test_file_contents_a modified"

class TestChatGPT(unittest.TestCase):
    def test_function1(self):
        # Replace 'function1' with the actual function name and add test logic
        result = ChatGPT.function1(input)
        self.assertEqual(result, expected_output)

    def test_function2(self):
        # Replace 'function2' with the actual function name and add test logic
        result = ChatGPT.function2(input)
        self.assertEqual(result, expected_output)

    # Add more test functions as needed

if __name__ == "__main__":
    unittest.main()

