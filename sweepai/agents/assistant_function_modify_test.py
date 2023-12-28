import unittest
from unittest.mock import Mock

from sweepai.agents.assistant_function_modify import function_modify


class TestFunctionModify(unittest.TestCase):
    def test_merge_conflict(self):
        # Create mock objects for the inputs
        request = 'merge conflict test'
        file_path = 'test.py'
        file_contents = '<<<<<<<\nconflict code\n>>>>>>>\n'
        additional_messages = []
        chat_logger = Mock()
        assistant_id = 'test_id'
        start_line = 0
        end_line = 3
        ticket_progress = Mock()
        assistant_conversation = Mock()
        seed = 0

        # Call the function with the mock objects as inputs
        result = function_modify(request, file_path, file_contents, additional_messages, chat_logger, assistant_id, start_line, end_line, ticket_progress, assistant_conversation, seed)

        # Check that the function correctly identifies the merge conflict
        self.assertIsNotNone(result)

    def test_no_merge_conflict(self):
        # Create mock objects for the inputs
        request = 'no merge conflict test'
        file_path = 'test.py'
        file_contents = 'valid code\n'
        additional_messages = []
        chat_logger = Mock()
        assistant_id = 'test_id'
        start_line = 0
        end_line = 1
        ticket_progress = Mock()
        assistant_conversation = Mock()
        seed = 0

        # Call the function with the mock objects as inputs
        result = function_modify(request, file_path, file_contents, additional_messages, chat_logger, assistant_id, start_line, end_line, ticket_progress, assistant_conversation, seed)

        # Check that the function correctly identifies that there is no merge conflict
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
