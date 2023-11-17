import unittest
from unittest.mock import patch, Mock

from complete_code import complete_code, ExtractLeftoverComments


class TestCompleteCode(unittest.TestCase):
    def setUp(self):
        self.mock_check_comments_presence = Mock()
        self.mock_chat = Mock()
        self.mock_from_string = Mock()
        self.extractor = ExtractLeftoverComments()

    @patch("complete_code.CONSTANT", "new constant")
    @patch("complete_code.complete_code")
    def test_complete_code(self, mock_complete_code):
        mock_complete_code.return_value = "forced value"
        
        # Call the function with the parameters you want to test
        result = complete_code("test input")

        # Assert that the mocked function was called with the right parameters
        mock_complete_code.assert_called_with("test input")
    @patch("sweepai.agents.complete_code.ExtractLeftoverComments.chat", new_callable=lambda: self.mock_chat)
    @patch("sweepai.agents.complete_code.LeftoverComments.from_string", new_callable=lambda: self.mock_from_string)
    def test_extract_leftover_comments_no_comments(self, mock_check_comments_presence, mock_chat, mock_from_string):
        new_code = "new code"
        file_path = "file_path"
        request = "request"
        leftover_comments = self.extractor.extract_leftover_comments(new_code, file_path, request)
        self.assertEqual(leftover_comments, [])


