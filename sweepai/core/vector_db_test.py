import unittest
from unittest.mock import patch, MagicMock
from sweepai.core.vector_db import embed_texts, get_deeplake_vs_from_repo, get_relevant_snippets
from sweepai.utils.github_utils import ClonedRepo
from sweepai.config.client import SweepConfig

class TestVectorDB(unittest.TestCase):

    @patch('sweepai.core.vector_db.SentenceTransformer')
    def test_embed_texts(self, mock_transformer):
        mock_transformer.return_value.encode.return_value = [0.1, 0.2, 0.3]
        result = embed_texts(('text1', 'text2', 'text3'))
        self.assertEqual(result, [0.1, 0.2, 0.3])

    @patch('sweepai.core.vector_db.get_blocked_dirs')
    @patch('sweepai.core.vector_db.prepare_lexical_search_index')
    @patch('sweepai.core.vector_db.compute_vector_search_scores')
    @patch('sweepai.core.vector_db.prepare_documents_metadata_ids')
    @patch('sweepai.core.vector_db.compute_deeplake_vs')
    def test_get_deeplake_vs_from_repo(self, mock_compute_deeplake_vs, mock_prepare_documents_metadata_ids, mock_compute_vector_search_scores, mock_prepare_lexical_search_index, mock_get_blocked_dirs):
        mock_repo = MagicMock()
        mock_repo.get_commits.return_value = [MagicMock(sha='commit_hash')]
        cloned_repo = ClonedRepo(repo_full_name='repo_full_name', installation_id='installation_id')
        sweep_config = SweepConfig()
        mock_get_blocked_dirs.return_value = []
        mock_prepare_lexical_search_index.return_value = ('file_list', 'snippets', 'index')
        mock_compute_vector_search_scores.return_value = 'files_to_scores'
        mock_prepare_documents_metadata_ids.return_value = ('collection_name', 'documents', 'ids', 'metadatas')
        mock_compute_deeplake_vs.return_value = 'deeplake_vs'
        result = get_deeplake_vs_from_repo(cloned_repo, sweep_config)
        self.assertEqual(result, ('deeplake_vs', 'index', len('documents')))

    @patch('sweepai.core.vector_db.embedding_function')
    @patch('sweepai.core.vector_db.get_deeplake_vs_from_repo')
    @patch('sweepai.core.vector_db.search_index')
    def test_get_relevant_snippets(self, mock_search_index, mock_get_deeplake_vs_from_repo, mock_embedding_function):
        mock_repo = MagicMock()
        cloned_repo = ClonedRepo(repo_full_name='repo_full_name', installation_id='installation_id')
        sweep_config = SweepConfig()
        query = 'query'
        mock_embedding_function.return_value = 'query_embedding'
        mock_get_deeplake_vs_from_repo.return_value = ('deeplake_vs', 'lexical_index', 'num_docs')
        mock_search_index.return_value = 'content_to_lexical_score'
        result = get_relevant_snippets(cloned_repo, query, sweep_config=sweep_config)
        self.assertEqual(result, [])

if __name__ == '__main__':
    unittest.main()
