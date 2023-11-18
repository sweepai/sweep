import unittest
from unittest.mock import MagicMock, patch

from sweepai.agents.complete_code import ExtractLeftoverComments


class TestExtractLeftoverComments(unittest.TestCase):
    @patch("sweepai.agents.complete_code.LeftoverComments.from_string")
    @patch("sweepai.agents.complete_code.ExtractLeftoverComments.chat")
    @patch("sweepai.agents.complete_code.check_comments_presence")
    def test_extract_leftover_comments(
        self, mock_check_comments_presence, mock_chat, mock_from_string
    ):
        # Arrange
        mock_check_comments_presence.return_value = True
        mock_chat.return_value = "mock_response"

        mock_leftover_comments = MagicMock()
        mock_leftover_comments.leftover_comments = "mock_leftover_comments"
        mock_from_string.return_value = mock_leftover_comments

        extract_leftover_comments = ExtractLeftoverComments()

        # Act
        result = extract_leftover_comments.extract_leftover_comments(
            "new_code", "file_path", "request"
        )

        # Assert
        self.assertEqual(result, "mock_leftover_comments")


if __name__ == "__main__":
    unittest.main()
