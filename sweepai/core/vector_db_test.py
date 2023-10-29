import unittest
from unittest.mock import patch, MagicMock
from sweepai.core.vector_db import fetch_repository, compute_embeddings, initialize_vectorstore
from sweepai.config.client import SweepConfig
from sweepai.utils.github_utils import ClonedRepo

class TestVectorDBFunctions(unittest.TestCase):

    @patch('sweepai.core.vector_db.get_blocked_dirs')
    @patch('sweepai.core.vector_db.repo_to_chunks')
    @patch('sweepai.core.vector_db.prepare_index_from_snippets')
    @patch('sweepai.core.vector_db.compute_score')
    @patch('sweepai.core.vector_db.get_scores')
    @patch('sweepai.core.vector_db.parse_collection_name')
    def test_fetch_repository(self, mock_parse_collection_name, mock_get_scores, mock_compute_score, mock_prepare_index_from_snippets, mock_repo_to_chunks, mock_get_blocked_dirs):
        mock_cloned_repo = MagicMock(spec=ClonedRepo)
        mock_sweep_config = SweepConfig()
        mock_parse_collection_name.return_value = 'collection_name'
        mock_get_scores.return_value = [0.5]
        mock_compute_score.return_value = 0.5
        mock_prepare_index_from_snippets.return_value = 'index'
        mock_repo_to_chunks.return_value = ([], [])
        mock_get_blocked_dirs.return_value = []

        result = fetch_repository(mock_cloned_repo, mock_sweep_config)

        self.assertEqual(result, ('collection_name', [], [], [], None))

    def test_compute_embeddings(self):
        documents = ['doc1', 'doc2', 'doc3']

        result = compute_embeddings(documents)

        self.assertIsNone(result)

    @patch('sweepai.core.vector_db.init_deeplake_vs')
    def test_initialize_vectorstore(self, mock_init_deeplake_vs):
        collection_name = 'collection_name'
        documents = ['doc1', 'doc2', 'doc3']
        ids = ['id1', 'id2', 'id3']
        metadatas = ['metadata1', 'metadata2', 'metadata3']
        sha = 'sha'
        embeddings = ['embedding1', 'embedding2', 'embedding3']
        mock_init_deeplake_vs.return_value = 'deeplake_vs'

        result = initialize_vectorstore(collection_name, documents, ids, metadatas, sha, embeddings)

        self.assertEqual(result, 'deeplake_vs')

if __name__ == '__main__':
    unittest.main()
