import unittest
from unittest.mock import Mock, patch
from sweepai.utils.github_utils import ClonedRepo
from sweepai.core.vector_db import embed_texts, get_deeplake_vs_from_repo, get_relevant_snippets

class TestVectorDb(unittest.TestCase):
    def setUp(self):
        self.mock_repo = Mock(spec=ClonedRepo)

    test_get_relevant_snippets_function()

    test_get_deeplake_vs_from_repo_function()

    test_embed_texts_function()

def test_get_relevant_snippets_function():
    @patch('sweepai.core.vector_db.embed_texts')
    def test_embed_texts(self, mock_embed_texts):
        mock_embed_texts.return_value = ['mock_embedding']
        result = embed_texts(['mock_text'])
        self.assertEqual(result, ['mock_embedding'])

def test_get_deeplake_vs_from_repo_function():
    @patch('sweepai.core.vector_db.get_deeplake_vs_from_repo')
    def test_get_deeplake_vs_from_repo(self, mock_get_deeplake_vs_from_repo):
        mock_get_deeplake_vs_from_repo.return_value = ('mock_vs', 'mock_index', 1)
        result = get_deeplake_vs_from_repo(self.mock_repo)
        self.assertEqual(result, ('mock_vs', 'mock_index', 1))

def test_embed_texts_function():
    @patch('sweepai.core.vector_db.get_relevant_snippets')
    def test_get_relevant_snippets(self, mock_get_relevant_snippets):
        mock_get_relevant_snippets.return_value = ['mock_snippet']
        result = get_relevant_snippets(self.mock_repo, 'mock_query')
        self.assertEqual(result, ['mock_snippet'])

if __name__ == '__main__':
    unittest.main()
