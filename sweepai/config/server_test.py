import unittest
from unittest.mock import patch
from sweepai.config import server

class TestServerConfig(unittest.TestCase):
    @patch.dict('os.environ', {'GITHUB_APP_ID': None, 'APP_ID': 'test_app_id'})
    def test_app_id_fallback(self):
        self.assertEqual(server.GITHUB_APP_ID, 'test_app_id')

    @patch.dict('os.environ', {'GITHUB_APP_ID': 'test_github_app_id', 'APP_ID': 'test_app_id'})
    def test_app_id_precedence(self):
        self.assertEqual(server.GITHUB_APP_ID, 'test_github_app_id')

if __name__ == '__main__':
    unittest.main()
