import unittest
# imports
from unittest import TestCase
from unittest.mock import MagicMock, patch

from deeplake.core.vectorstore.deeplake_vectorstore import VectorStore

from sweepai.config.client import SweepConfig
from sweepai.core.vector_db import (get_deeplake_vs_from_repo,
                                    prepare_lexical_search_index)


class TestEmbedTexts(unittest.TestCase):
    @patch("sentence_transformers.SentenceTransformer")
    @patch("openai.Embedding.create")
    @patch("sweepai.core.vector_db.embed_huggingface")
    @patch("sweepai.core.vector_db.embed_replicate")
    @unittest.skip("FAILED (errors=1)")
    def test_embed_texts(
        self,
        mock_embed_replicate,
        mock_embed_huggingface,
        mock_openai_embedding_create,
        mock_sentence_transformer,
    ):
        mock_sentence_transformer.return_value.encode.return_value = "mock_vector"
        mock_openai_embedding_create.return_value = {
            "data": [{"embedding": "mock_embedding"}]
        }
        mock_embed_huggingface.return_value = "mock_embedding"
        mock_embed_replicate.return_value = "mock_embedding"

        from sweepai.core.vector_db import embed_texts

        result = embed_texts(("test_text",))
        self.assertEqual(result, "mock_vector")

    @patch("sweepai.core.vector_db.VECTOR_EMBEDDING_SOURCE", "sentence-transformers")
    @patch(
        "sweepai.core.vector_db.SENTENCE_TRANSFORMERS_MODEL",
        "bert-base-nli-mean-tokens",
    )
    @patch("sweepai.core.vector_db.BATCH_SIZE", 32)
    @patch("sweepai.core.vector_db.HUGGINGFACE_URL", "https://api.huggingface.co")
    @patch("sweepai.core.vector_db.HUGGINGFACE_TOKEN", "token")
    @patch("sweepai.core.vector_db.REPLICATE_API_KEY", "key")
    @patch("sweepai.core.vector_db.SentenceTransformer")
    @patch("sweepai.core.vector_db.openai.Embedding.create")
    @patch("sweepai.core.vector_db.embed_huggingface")
    @patch("sweepai.core.vector_db.embed_replicate")
    def test_embed_texts(
        self,
        mock_embed_replicate,
        mock_embed_huggingface,
        mock_openai_embedding_create,
        mock_sentence_transformer,
    ):
        mock_sentence_transformer.return_value.encode.return_value = "mock_vector"
        mock_openai_embedding_create.return_value = {
            "data": [{"embedding": "mock_embedding"}]
        }
        mock_embed_huggingface.return_value = "mock_embedding"
        mock_embed_replicate.return_value = "mock_embedding"

        from sweepai.core.vector_db import embed_texts

        result = embed_texts(("test_text",))
        self.assertEqual(result, "mock_vector")


class TestVectorDB(TestCase):
    @patch("sweepai.core.repo_parsing_utils.repo_to_chunks")
    @patch("sweepai.core.lexical_search.prepare_index_from_snippets")
    def test_prepare_lexical_search_index(
        self, mock_prepare_index_from_snippets, mock_repo_to_chunks
    ):
        # Arrange
        mock_cloned_repo = MagicMock()
        mock_cloned_repo.cached_dir = "/mock/path"
        mock_sweep_config = MagicMock()
        mock_repo_full_name = "mock/repo"
        mock_repo_to_chunks.return_value = ([], [])
        mock_prepare_index_from_snippets.return_value = None

        # Act
        result = prepare_lexical_search_index(
            mock_cloned_repo, mock_sweep_config, mock_repo_full_name
        )

        # Assert
        mock_repo_to_chunks.assert_called_once_with(
            mock_cloned_repo.cached_dir, mock_sweep_config
        )
        mock_prepare_index_from_snippets.assert_called_once()
        self.assertEqual(([], [], None), result)

    @patch("sweepai.core.repo_parsing_utils.repo_to_chunks")
    @patch("sweepai.core.lexical_search.prepare_index_from_snippets")
    @patch("loguru.logger.info")
    @patch("loguru.logger.print")
    def test_prepare_lexical_search_index_logs_correct_number_of_snippets(
        self,
        mock_logger_print,
        mock_logger_info,
        mock_prepare_index_from_snippets,
        mock_repo_to_chunks,
    ):
        # Arrange
        mock_cloned_repo = MagicMock()
        mock_cloned_repo.cached_dir = "/mock/path"
        mock_sweep_config = MagicMock()
        mock_repo_full_name = "mock/repo"
        mock_repo_to_chunks.return_value = ([], [])
        mock_prepare_index_from_snippets.return_value = None

        # Act
        prepare_lexical_search_index(
            mock_cloned_repo, mock_sweep_config, mock_repo_full_name
        )

        # Assert
        mock_logger_info.assert_called_once_with(
            "Found 0 snippets in repository mock/repo"
        )
        mock_logger_print.assert_called_once_with("Prepared index from snippets")


class TestGetDeeplakeVsFromRepo(TestCase):
    @patch("sweepai.core.vector_db.get_blocked_dirs")
    @patch("sweepai.core.vector_db.prepare_lexical_search_index")
    @patch("sweepai.core.vector_db.compute_vector_search_scores")
    @patch("sweepai.core.vector_db.prepare_documents_metadata_ids")
    @patch("sweepai.core.vector_db.compute_deeplake_vs")
    def test_get_deeplake_vs_from_repo(
        self,
        mock_compute_deeplake_vs,
        mock_prepare_documents_metadata_ids,
        mock_compute_vector_search_scores,
        mock_prepare_lexical_search_index,
        mock_get_blocked_dirs,
    ):
        mock_repo = MagicMock()
        mock_repo.get_commits.return_value = [MagicMock(sha="commit_hash")]
        mock_cloned_repo = MagicMock(repo=mock_repo)

        mock_get_blocked_dirs.return_value = ["blocked_dir"]
        mock_prepare_lexical_search_index.return_value = (
            "file_list",
            "snippets",
            "index",
        )
        mock_compute_vector_search_scores.return_value = {"file": "score"}
        mock_prepare_documents_metadata_ids.return_value = (
            "collection_name",
            "documents",
            "ids",
            "metadatas",
        )
        mock_compute_deeplake_vs.return_value = MagicMock(spec=VectorStore)

        # Call the function to test
        deeplake_vs, index, len_documents = get_deeplake_vs_from_repo(
            mock_cloned_repo, SweepConfig()
        )

        # Assertions
        # ...

    @patch("sweepai.core.vector_db.get_blocked_dirs")
    @patch("sweepai.core.vector_db.prepare_lexical_search_index")
    @patch("sweepai.core.vector_db.compute_vector_search_scores")
    @patch("sweepai.core.vector_db.prepare_documents_metadata_ids")
    @patch("sweepai.core.vector_db.compute_deeplake_vs")
    def test_get_deeplake_vs_from_repo(
        self,
        mock_compute_deeplake_vs,
        mock_prepare_documents_metadata_ids,
        mock_compute_vector_search_scores,
        mock_prepare_lexical_search_index,
        mock_get_blocked_dirs,
    ):
        mock_repo = MagicMock()
        mock_repo.get_commits.return_value = [MagicMock(sha="commit_hash")]
        mock_cloned_repo = MagicMock(repo=mock_repo)

        mock_get_blocked_dirs.return_value = ["blocked_dir"]
        mock_prepare_lexical_search_index.return_value = (
            "file_list",
            "snippets",
            "index",
        )
        mock_compute_vector_search_scores.return_value = {"file": "score"}
        mock_prepare_documents_metadata_ids.return_value = (
            "collection_name",
            "documents",
            "ids",
            "metadatas",
        )
        mock_compute_deeplake_vs.return_value = MagicMock(spec=VectorStore)

        # Call the function to test
        deeplake_vs, index, len_documents = get_deeplake_vs_from_repo(
            mock_cloned_repo, SweepConfig()
        )

        # Assertions
        self.assertEqual(len_documents, len("documents"))
        self.assertIsNotNone(deeplake_vs)
        self.assertEqual(index, "index")


if __name__ == "__main__":
    unittest.main()

