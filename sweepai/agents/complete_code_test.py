import unittest
from unittest.mock import MagicMock, patch

from sweepai.agents.complete_code import ExtractLeftoverComments


class TestExtractLeftoverCommentsExtractLeftoverComments(unittest.TestCase):
    def setUp(self):
        self.extractor = ExtractLeftoverComments()
        self.mock_check_comments_presence = MagicMock(return_value=True)
        self.mock_chat = MagicMock(return_value="mock_response")
        self.mock_leftover_comments = MagicMock()
        self.mock_leftover_comments.leftover_comments = ["mock_comment"]

    @patch("sweepai.agents.complete_code.check_comments_presence", return_value=True)
    @patch(
        "sweepai.agents.complete_code.ExtractLeftoverComments.chat",
        return_value="mock_response",
    )
    @patch(
        "sweepai.agents.complete_code.LeftoverComments.from_string",
        return_value=mock_leftover_comments,
    )
    def test_extract_leftover_comments(
        self, mock_check_comments_presence, mock_chat, mock_leftover_comments
    ):
        result = self.extractor.extract_leftover_comments(
            "new_code", "file_path", "request"
        )
        self.assertEqual(result, ["mock_comment"])

    @patch("sweepai.agents.complete_code.check_comments_presence", return_value=True)
    @patch(
        "sweepai.agents.complete_code.ExtractLeftoverComments.chat",
        return_value="mock_response",
    )
    @patch(
        "sweepai.agents.complete_code.LeftoverComments.from_string",
        return_value=mock_leftover_comments,
    )
    def test_extract_leftover_comments(
        self, mock_check_comments_presence, mock_chat, mock_leftover_comments
    ):
        result = self.extractor.extract_leftover_comments(
            "new_code", "file_path", "request"
        )
        self.assertEqual(result, ["mock_comment"])

    @patch("sweepai.agents.complete_code.check_comments_presence", return_value=False)
    @patch(
        "sweepai.agents.complete_code.ExtractLeftoverComments.chat",
        return_value="mock_response",
    )
    @patch(
        "sweepai.agents.complete_code.LeftoverComments.from_string",
        return_value=mock_leftover_comments,
    )
    def test_extract_leftover_comments_no_comments(
        self, mock_check_comments_presence, mock_chat, mock_leftover_comments
    ):
        result = self.extractor.extract_leftover_comments(
            "new_code", "file_path", "request"
        )
        self.assertEqual(result, [])
        mock_chat.assert_not_called()
        mock_leftover_comments.assert_not_called()


if __name__ == "__main__":
    unittest.main()
