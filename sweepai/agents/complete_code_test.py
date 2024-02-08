import unittest
from unittest.mock import MagicMock, patch

from sweepai.agents.complete_code import ExtractLeftoverComments


class TestExtractLeftoverCommentsExtractLeftoverComments(unittest.TestCase):
    @patch("sweepai.agents.complete_code.check_comments_presence")
    @patch("sweepai.agents.complete_code.ExtractLeftoverComments.chat")
    @patch("sweepai.agents.complete_code.LeftoverComments.from_string")
    def test_extract_leftover_comments(
        self, mock_from_string, mock_chat, mock_check_comments_presence
    ):
        mock_check_comments_presence.return_value = True
        mock_chat.return_value = "mock response"
        mock_from_string.return_value = MagicMock()
        mock_from_string.return_value.leftover_comments = []

        extract_leftover_comments = ExtractLeftoverComments(chat_logger=None)
        result = extract_leftover_comments.extract_leftover_comments(
            "new_code", "file_path", "request"
        )
        self.assertEqual(result, [])

    @patch("sweepai.agents.complete_code.check_comments_presence")
    @patch("sweepai.agents.complete_code.ExtractLeftoverComments.chat")
    @patch("sweepai.agents.complete_code.LeftoverComments.from_string")
    def test_extract_leftover_comments_no_comments(
        self, mock_from_string, mock_chat, mock_check_comments_presence
    ):
        mock_check_comments_presence.return_value = False

        extract_leftover_comments = ExtractLeftoverComments(chat_logger=None)
        result = extract_leftover_comments.extract_leftover_comments(
            "new_code", "file_path", "request"
        )
        self.assertEqual(result, [])
        mock_chat.assert_not_called()
        mock_from_string.assert_not_called()


if __name__ == "__main__":
    unittest.main()
