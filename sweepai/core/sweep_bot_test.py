import unittest
from unittest.mock import patch
from sweepai.core.sweep_bot import is_blocked

class TestIsBlocked(unittest.TestCase):

    def test_is_blocked_with_blocked_dir(self):
        file_path = "blocked_dir/sub_dir/file.py"
        blocked_dirs = ["blocked_dir"]
        expected_output = {"success": True, "path": "blocked_dir"}
        self.assertEqual(is_blocked(file_path, blocked_dirs), expected_output)

    def test_is_blocked_without_blocked_dir(self):
        file_path = "unblocked_dir/sub_dir/file.py"
        blocked_dirs = ["blocked_dir"]
        expected_output = {"success": False}
        self.assertEqual(is_blocked(file_path, blocked_dirs), expected_output)

    def test_is_blocked_with_empty_blocked_dir(self):
        file_path = "any_dir/sub_dir/file.py"
        blocked_dirs = []
        expected_output = {"success": False}
        self.assertEqual(is_blocked(file_path, blocked_dirs), expected_output)

    def test_is_blocked_with_none_blocked_dir(self):
        file_path = "any_dir/sub_dir/file.py"
        blocked_dirs = None
        expected_output = {"success": False}
        self.assertEqual(is_blocked(file_path, blocked_dirs), expected_output)

if __name__ == "__main__":
    unittest.main()
