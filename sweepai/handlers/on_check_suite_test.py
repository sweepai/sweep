from unittest.mock import patch

import pytest

from sweepai.handlers.on_check_suite import clean_logs


class TestCleanLogs:
    def test_clean_logs_with_empty_string(self):
        logs_str = ""
        expected_output = "", ""
        assert clean_logs(logs_str) == expected_output

    def test_clean_logs_with_valid_logs(self):
        logs_str = "##[group]Test Group##[endgroup]Test Content##[error]Test Error"
        expected_output = ("The command:\nTest Group\nyielded the following error:\nTest Error\n\nHere are the logs:\nTest Content", 
                           "The command:\n`Test Group`\nyielded the following error:\n`Test Error`\nHere are the logs:\n```\nTest Content\n```")
        assert clean_logs(logs_str) == expected_output

    @patch('re.search')
    def test_clean_logs_with_mocked_re_search(self, mock_search):
        mock_search.return_value = None
        logs_str = "##[group]Test Group##[endgroup]Test Content##[error]Test Error"
        expected_output = "", ""
        assert clean_logs(logs_str) == expected_output
