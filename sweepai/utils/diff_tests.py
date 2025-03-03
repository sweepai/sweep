import unittest
from unittest.mock import patch
from sweepai.utils.diff import revert_whitespace_changes, format_contents, match_string, is_markdown

class TestDiffFunctions(unittest.TestCase):

    @patch('sweepai.utils.search_and_replace.Match')
    @patch('sweepai.logn.logger')
    @patch('sweepai.utils.chat_logger.discord_log_error')
    def test_revert_whitespace_changes(self, mock_match, mock_logger, mock_discord_log_error):
        # Test cases for revert_whitespace_changes function
        self.assertEqual(revert_whitespace_changes('  hello  '), 'hello')
        self.assertEqual(revert_whitespace_changes('hello'), 'hello')

    @patch('sweepai.utils.search_and_replace.Match')
    @patch('sweepai.logn.logger')
    @patch('sweepai.utils.chat_logger.discord_log_error')
    def test_format_contents(self, mock_match, mock_logger, mock_discord_log_error):
        # Test cases for format_contents function
        self.assertEqual(format_contents('hello'), 'hello')
        self.assertEqual(format_contents('  hello  '), 'hello')

    @patch('sweepai.utils.search_and_replace.Match')
    @patch('sweepai.logn.logger')
    @patch('sweepai.utils.chat_logger.discord_log_error')
    def test_match_string(self, mock_match, mock_logger, mock_discord_log_error):
        # Test cases for match_string function
        self.assertTrue(match_string('hello', 'hello'))
        self.assertFalse(match_string('hello', 'world'))

    @patch('sweepai.utils.search_and_replace.Match')
    @patch('sweepai.logn.logger')
    @patch('sweepai.utils.chat_logger.discord_log_error')
    def test_is_markdown(self, mock_match, mock_logger, mock_discord_log_error):
        # Test cases for is_markdown function
        self.assertTrue(is_markdown('test.md'))
        self.assertFalse(is_markdown('test.txt'))

if __name__ == "__main__":
    unittest.main()
