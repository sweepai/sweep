import unittest
from unittest.mock import patch
from sweepai.core.sweep_bot import GithubBot, FileChangeRequest

class TestGithubBot(unittest.TestCase):
    def setUp(self):
        self.github_bot = GithubBot()

    @patch('sweepai.core.sweep_bot.GithubBot.get_contents')
    def test_validate_file_change_requests_modify(self, mock_get_contents):
        mock_get_contents.return_value = 'mock file content'
        file_change_request = FileChangeRequest(filename='test.py', change_type='modify')
        result = self.github_bot.validate_file_change_requests([file_change_request])
        self.assertEqual(result[0].change_type, 'modify')

    @patch('sweepai.core.sweep_bot.GithubBot.get_contents')
    def test_validate_file_change_requests_create(self, mock_get_contents):
        mock_get_contents.side_effect = FileNotFoundError
        file_change_request = FileChangeRequest(filename='test.py', change_type='modify')
        result = self.github_bot.validate_file_change_requests([file_change_request])
        self.assertEqual(result[0].change_type, 'create')

    def test_validate_file_change_requests_blocked(self):
        file_change_request = FileChangeRequest(filename='blocked/test.py', change_type='modify')
        result = self.github_bot.validate_file_change_requests([file_change_request], blocked_dirs=['blocked'])
        self.assertTrue('Unable to modify files' in result[0].instructions)

if __name__ == '__main__':
    unittest.main()
