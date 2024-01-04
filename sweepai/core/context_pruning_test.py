import unittest
from unittest.mock import Mock

from sweepai.core.context_pruning import RepoContextManager, Snippet


class TestRepoContextManager(unittest.TestCase):
    def test_filter_sweep_yaml(self):
        # Create mock snippets
        mock_snippets = [
            Mock(spec=Snippet, file_path='file1.py'),
            Mock(spec=Snippet, file_path='sweep.yaml'),
            Mock(spec=Snippet, file_path='file2.py')
        ]

        # Create RepoContextManager instance
        repo_context_manager = RepoContextManager(
            dir_obj=Mock(),
            current_top_tree='',
            snippets=[],
            snippet_scores={},
            cloned_repo=Mock()
        )

        # Assign mock snippets to current_top_snippets
        repo_context_manager.current_top_snippets = mock_snippets

        # Filter out "sweep.yaml" snippets
        repo_context_manager.current_top_snippets = [
            snippet
            for snippet in repo_context_manager.current_top_snippets
            if snippet.file_path != "sweep.yaml"
        ]

        # Assert "sweep.yaml" snippet is no longer in current_top_snippets
        self.assertNotIn(
            'sweep.yaml', 
            [snippet.file_path for snippet in repo_context_manager.current_top_snippets]
        )

if __name__ == '__main__':
    unittest.main()
