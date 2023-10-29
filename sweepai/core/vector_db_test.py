import unittest
from unittest.mock import patch, MagicMock
from sweepai.core.vector_db import get_deeplake_vs_from_repo, get_relevant_snippets
from sweepai.config.client import SweepConfig
from sweepai.utils.github_utils import ClonedRepo

class TestVectorDB(unittest.TestCase):

    @patch('sweepai.core.vector_db.get_blocked_dirs')
    @patch('sweepai.core.vector_db.repo_to_chunks')
    @patch('sweepai.core.vector_db.prepare_index_from_snippets')
    def test_get_deeplake_vs_from_repo(self, mock_prepare_index, mock_repo_to_chunks, mock_get_blocked_dirs):
        mock_get_blocked_dirs.return_value = ['dir1', 'dir2']
        mock_repo_to_chunks.return_value = ([], [])
        mock_prepare_index.return_value = None

        cloned_repo = ClonedRepo('repo_name', installation_id=123)
        sweep_config = SweepConfig()

        result = get_deeplake_vs_from_repo(cloned_repo, sweep_config)

        self.assertEqual(result, (None, None, 0))
        mock_get_blocked_dirs.assert_called_once()
        mock_repo_to_chunks.assert_called_once_with(cloned_repo.cache_dir, sweep_config)
        mock_prepare_index.assert_called_once_with([], len(cloned_repo.cache_dir) + 1)

    @patch('sweepai.core.vector_db.get_deeplake_vs_from_repo')
    @patch('sweepai.core.vector_db.search_index')
    def test_get_relevant_snippets(self, mock_search_index, mock_get_deeplake_vs):
        mock_search_index.return_value = {}
        mock_get_deeplake_vs.return_value = (MagicMock(), MagicMock(), 10)

        cloned_repo = ClonedRepo('repo_name', installation_id=123)
        sweep_config = SweepConfig()

        result = get_relevant_snippets(cloned_repo, 'query')

        self.assertEqual(result, [])
        mock_search_index.assert_called_once_with('query', mock_get_deeplake_vs.return_value[1])
        mock_get_deeplake_vs.assert_called_once_with(cloned_repo, sweep_config)

if __name__ == '__main__':
    unittest.main()
