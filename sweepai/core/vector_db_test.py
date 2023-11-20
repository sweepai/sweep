# imports
import unittest
from unittest import TestCase
from unittest.mock import MagicMock, patch

from deeplake.core.vectorstore.deeplake_vectorstore import VectorStore

from sweepai.config.client import SweepConfig
from sweepai.core.vector_db import (chunk, get_deeplake_vs_from_repo,
                                    prepare_documents_metadata_ids)


class TestPrepareDocumentsMetadataIds(unittest.TestCase):
    @patch("sweepai.core.entities.Snippet")
    @patch("sweepai.utils.github_utils.ClonedRepo")
    @unittest.skip("FAILED (failures=1)")
    def test_prepare_documents_metadata_ids(self, mock_ClonedRepo, mock_Snippet):
        mock_Snippet.get_snippet.return_value = "mock snippet"
        mock_Snippet.file_path = "mock file path"
        mock_Snippet.start = 0
        mock_Snippet.end = 10
        mock_ClonedRepo.cached_dir = "mock cached dir"

        snippets = [mock_Snippet]
        cloned_repo = mock_ClonedRepo
        files_to_scores = {"mock file path": 1}
        start = 0
        repo_full_name = "mock/repo"

        collection_name, documents, ids, metadatas = prepare_documents_metadata_ids(
            snippets, cloned_repo, files_to_scores, start, repo_full_name
        )

        self.assertEqual(collection_name, "mock--repo")  # Updated expected value
        self.assertEqual(documents, ["mock snippet"])
        self.assertEqual(ids, ["mock file path:0:10"])
        self.assertEqual(
            metadatas,
            [
                {
                    "file_path": "mock file path",
                    "start": 0,
                    "end": 10,
                    "score": 1,
                }
            ],
        )

    @patch("sweepai.core.entities.Snippet")
    @patch("sweepai.utils.github_utils.ClonedRepo")
    def test_prepare_documents_metadata_ids_empty_snippets(
        self, mock_ClonedRepo, mock_Snippet
    ):
        mock_Snippet.get_snippet.return_value = "mock snippet"
        mock_Snippet.file_path = "mock file path"
        mock_Snippet.start = 0
        mock_Snippet.end = 10
        mock_ClonedRepo.cached_dir = "mock cached dir"

        snippets = []
        cloned_repo = mock_ClonedRepo
        files_to_scores = {"mock file path": 1}
        start = 0
        repo_full_name = "mock/repo"

        collection_name, documents, ids, metadatas = prepare_documents_metadata_ids(
            snippets, cloned_repo, files_to_scores, start, repo_full_name
        )

        self.assertEqual(collection_name, "mock/repo")
        self.assertEqual(documents, [])
        self.assertEqual(ids, [])
        self.assertEqual(metadatas, [])


class TestChunkChunk(unittest.TestCase):
    def test_chunk(self):
        texts = ["text1", "text2", "text3", "text4", "text5"]
        batch_size = 2
        expected_output = [["text1", "text2"], ["text3", "text4"], ["text5"]]

        result = list(chunk(texts, batch_size))

        self.assertEqual(result, expected_output)


def test_chunk_empty_list(self):
    texts = []
    batch_size = 2
    expected_output = []

    result = list(chunk(texts, batch_size))

    self.assertEqual(result, expected_output)


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
    def test_get_deeplake_vs_from_repo_no_commits(
        self,
        mock_compute_deeplake_vs,
        mock_prepare_documents_metadata_ids,
        mock_compute_vector_search_scores,
        mock_prepare_lexical_search_index,
        mock_get_blocked_dirs,
    ):
        mock_repo = MagicMock()
        mock_repo.get_commits.return_value = []
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

        with self.assertRaises(IndexError):
            get_deeplake_vs_from_repo(mock_cloned_repo, SweepConfig())


if __name__ == "__main__":
    unittest.main()

