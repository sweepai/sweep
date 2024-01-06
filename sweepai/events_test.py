import unittest
from unittest.mock import Mock

from sweepai.events import CheckRunCompleted


class TestCheckSuite(unittest.TestCase):
    def test_head_branch_string(self):
        mock_check_run = Mock(spec=CheckRunCompleted)
        mock_check_run.check_suite.head_branch = "test_branch"
        self.assertEqual(mock_check_run.check_suite.head_branch, "test_branch")

    def test_head_branch_none(self):
        mock_check_run = Mock(spec=CheckRunCompleted)
        mock_check_run.check_suite.head_branch = None
        self.assertEqual(mock_check_run.check_suite.head_branch, None)

if __name__ == "__main__":
    unittest.main()
