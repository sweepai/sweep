import unittest
from unittest.mock import MagicMock, patch

from sweepai.agents.complete_code import ExtractLeftoverComments


class TestExtractLeftoverCommentsExtractLeftoverComments(unittest.TestCase):
    def setUp(self):
        self.extract_leftover_comments = ExtractLeftoverComments()
        self.mock_check_comments_presence = MagicMock(return_value=True)
        self.mock_chat = MagicMock(return_value="mock response")
        self.mock_from_string = MagicMock()
        self.mock_from_string.leftover_comments = ["mock comment"]

    @patch(
        "sweepai.agents.complete_code.check_comments_presence",
        new_callable=lambda: self.mock_check_comments_presence,
    )
    @patch(
        "sweepai.agents.complete_code.ExtractLeftoverComments.chat",
        new_callable=lambda: self.mock_chat,
    )
    @patch(
        "sweepai.agents.complete_code.LeftoverComments.from_string",
        new_callable=lambda: self.mock_from_string,
    )
    def test_extract_leftover_comments(self):
        result = self.extract_leftover_comments.extract_leftover_comments(
            "new_code", "file_path", "request"
        )
        self.assertEqual(result, ["mock comment"])

    @patch(
        "sweepai.agents.complete_code.check_comments_presence",
        new_callable=lambda: self.mock_check_comments_presence,
    )
    @patch(
        "sweepai.agents.complete_code.ExtractLeftoverComments.chat",
        new_callable=lambda: self.mock_chat,
    )
    @patch(
        "sweepai.agents.complete_code.LeftoverComments.from_string",
        new_callable=lambda: self.mock_from_string,
    )
    def test_extract_leftover_comments_no_comments(self):
        result = self.extract_leftover_comments.extract_leftover_comments(
            "new_code", "file_path", "request"
        )
        self.assertEqual(result, [])
        self.mock_chat.assert_not_called()
        self.mock_from_string.assert_not_called()


if __name__ == "__main__":
    unittest.main()
