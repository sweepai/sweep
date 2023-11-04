import unittest
from unittest.mock import patch, MagicMock
from sweepai.core.vector_db import embed_texts, get_deeplake_vs_from_repo, get_relevant_snippets
from sweepai.config.client import SweepConfig
from sweepai.utils.github_utils import ClonedRepo

class TestVectorDB(unittest.TestCase):
    @patch("sweepai.core.vector_db.SentenceTransformer")
    @patch("openai.Embedding.create")
    def test_embed_texts(self, mock_openai, mock_transformer):
        mock_transformer.return_value.encode.return_value = ["embedding1", "embedding2"]
        mock_openai.return_value = {"data": [{"embedding": "embedding3"}]}
        result = embed_texts(("text1", "text2"))
        self.assertEqual(result, ["embedding1", "embedding2", "embedding3"])
    @patch("sweepai.core.vector_db.prepare_lexical_search_index")
    @patch("sweepai.core.vector_db.compute_vector_search_scores")
    @patch("sweepai.core.vector_db.prepare_documents_metadata_ids")
    @patch("sweepai.core.vector_db.compute_deeplake_vs")
    def test_get_deeplake_vs_from_repo(self, mock_compute_deeplake_vs, mock_prepare_documents_metadata_ids, mock_compute_vector_search_scores, mock_prepare_lexical_search_index):
        mock_repo = MagicMock()
        mock_repo.repo_full_name = "test/repo"
        mock_compute_deeplake_vs.return_value = "deeplake_vs"
        result = get_deeplake_vs_from_repo(ClonedRepo(mock_repo, installation_id=None))
        self.assertEqual(result[0], "deeplake_vs")

    @patch("sweepai.core.vector_db.embedding_function")
    @patch("sweepai.core.vector_db.get_deeplake_vs_from_repo")
    @patch("sweepai.core.vector_db.search_index")
    def test_get_relevant_snippets(self, mock_search_index, mock_get_deeplake_vs_from_repo, mock_embedding_function):
        mock_repo = MagicMock()
        mock_repo.repo_full_name = "test/repo"
        mock_get_deeplake_vs_from_repo.return_value = ("deeplake_vs", "lexical_index", 10)
        mock_search_index.return_value = {"key": "value"}
        result = get_relevant_snippets(ClonedRepo(mock_repo, installation_id=None), "query")
        self.assertIsInstance(result, list)

if __name__ == "__main__":
    unittest.main()
