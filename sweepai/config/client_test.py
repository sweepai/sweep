import unittest
from unittest.mock import Mock
from sweepai.config.client import get_branch, get_gha_enabled

class TestClientConfigMethods(unittest.TestCase):
    def test_get_branch(self):
        mock_repo = Mock()
        mock_repo.default_branch = 'main'
        mock_repo.get_branch.return_value = 'main'
        mock_repo.get_contents.return_value.decoded_content.decode.return_value = 'branch: main'

        branch = get_branch(mock_repo)
        self.assertEqual(branch, 'main')

        mock_repo.get_branch.side_effect = Exception('Error')
        branch = get_branch(mock_repo)
        self.assertEqual(branch, 'main')

    def test_get_gha_enabled(self):
        mock_repo = Mock()
        mock_repo.get_contents.return_value.decoded_content.decode.return_value = 'gha_enabled: True'

        gha_enabled = get_gha_enabled(mock_repo)
        self.assertTrue(gha_enabled)

        mock_repo.get_contents.side_effect = Exception('Error')
        gha_enabled = get_gha_enabled(mock_repo)
        self.assertTrue(gha_enabled)

if __name__ == '__main__':
    unittest.main()
