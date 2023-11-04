import time
import unittest
from unittest.mock import patch, MagicMock
from deeplake.core.vectorstore.deeplake_vectorstore import VectorStore
from sweepai.config.client import SweepConfig
from sweepai.utils.github_utils import ClonedRepo
from sweepai.core.vector_db import (
    download_models,
    init_deeplake_vs,
    parse_collection_name,
    embed_huggingface,
    embed_replicate,
    embed_texts,
    embedding_function,
    get_deeplake_vs_from_repo,
    prepare_documents_metadata_ids,
    compute_vector_search_scores,
    prepare_lexical_search_index,
    compute_deeplake_vs,
    compute_embeddings,
    get_relevant_snippets,
)


class TestVectorDB(unittest.TestCase):
    @patch("sweepai.core.vector_db.SentenceTransformer")
    def test_download_models(self, mock_sentence_transformer):
        download_models()
        mock_sentence_transformer.assert_called_once()

    def test_init_deeplake_vs(self):
        vs = init_deeplake_vs("repo_name")
        self.assertIsInstance(vs, VectorStore)

    def test_parse_collection_name(self):
        self.assertEqual(parse_collection_name("repo/name"), "repo--name")

    @patch("sweepai.core.vector_db.requests.post")
    def test_embed_huggingface(self, mock_post):
        mock_post.return_value.json.return_value = {"embeddings": [1, 2, 3]}
        self.assertEqual(embed_huggingface(["text"]), [1, 2, 3])

    @patch("sweepai.core.vector_db.replicate.Client")
    def test_embed_replicate(self, mock_client):
        mock_client.return_value.deployments.get.return_value.predictions.create.return_value.wait.return_value = None
        mock_client.return_value.deployments.get.return_value.predictions.create.return_value.output = [{"embedding": [1, 2, 3]}]
        self.assertEqual(embed_replicate(["text"]), [[1, 2, 3]])

    @patch("sweepai.core.vector_db.SentenceTransformer")
    def test_embed_texts(self, mock_sentence_transformer):
        mock_sentence_transformer.return_value.encode.return_value = [1, 2, 3]
        self.assertEqual(embed_texts(("text",)), [1, 2, 3])

    @patch("sweepai.core.vector_db.SentenceTransformer")
    def test_embedding_function(self, mock_sentence_transformer):
        mock_sentence_transformer.return_value.encode.return_value = [1, 2, 3]
        self.assertEqual(embedding_function(["text"]), [1, 2, 3])

    @patch("sweepai.core.vector_db.prepare_lexical_search_index")
    @patch("sweepai.core.vector_db.compute_vector_search_scores")
    @patch("sweepai.core.vector_db.prepare_documents_metadata_ids")
    @patch("sweepai.core.vector_db.compute_deeplake_vs")
    def test_get_deeplake_vs_from_repo(self, mock_compute_deeplake_vs, mock_prepare_documents_metadata_ids, mock_compute_vector_search_scores, mock_prepare_lexical_search_index):
        mock_cloned_repo = MagicMock()
        mock_cloned_repo.repo_full_name = "repo_name"
        mock_cloned_repo.repo.get_commits.return_value = [MagicMock()]
        mock_compute_deeplake_vs.return_value = MagicMock()
        mock_prepare_lexical_search_index.return_value = ([], [], MagicMock())
        mock_compute_vector_search_scores.return_value = {}
        mock_prepare_documents_metadata_ids.return_value = ("", [], [], [])
        vs, index, num_docs = get_deeplake_vs_from_repo(mock_cloned_repo)
        self.assertIsInstance(vs, VectorStore)
        self.assertIsInstance(index, dict)
        self.assertEqual(num_docs, 0)

    def test_prepare_documents_metadata_ids(self):
        mock_snippets = [MagicMock() for _ in range(3)]
        mock_cloned_repo = MagicMock()
        mock_cloned_repo.cache_dir = "/tmp/cache/repos/repo_name"
        mock_files_to_scores = {"file1": 1, "file2": 2, "file3": 3}
        start = time.time()
        repo_full_name = "repo_name"
        collection_name, documents, ids, metadatas = prepare_documents_metadata_ids(mock_snippets, mock_cloned_repo, mock_files_to_scores, start, repo_full_name)
        self.assertEqual(collection_name, "repo_name")
        self.assertEqual(len(documents), 3)
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(metadatas), 3)

    @patch("sweepai.core.vector_db.compute_score")
    @patch("sweepai.core.vector_db.redis_client")
    def test_compute_vector_search_scores(self, mock_redis_client, mock_compute_score):
        mock_file_list = ["file1", "file2", "file3"]
        mock_cloned_repo = MagicMock()
        mock_cloned_repo.cache_dir = "/tmp/cache/repos/repo_name"
        repo_full_name = "repo_name"
        mock_compute_score.return_value = 1
        mock_redis_client.get.return_value = None
        files_to_scores = compute_vector_search_scores(mock_file_list, mock_cloned_repo, repo_full_name)
        self.assertEqual(files_to_scores, {"file1": 1, "file2": 1, "file3": 1})
        mock_redis_client.get.assert_called()
        mock_redis_client.set.assert_called()

    @patch("sweepai.core.vector_db.repo_to_chunks")
    def test_prepare_lexical_search_index(self, mock_repo_to_chunks):
        mock_cloned_repo = MagicMock()
        mock_cloned_repo.cache_dir = "/tmp/cache/repos/repo_name"
        sweep_config = SweepConfig()
        repo_full_name = "repo_name"
        mock_repo_to_chunks.return_value = ([], [])
        file_list, snippets, index = prepare_lexical_search_index(mock_cloned_repo, sweep_config, repo_full_name)
        self.assertEqual(file_list, [])
        self.assertEqual(snippets, [])
        self.assertIsInstance(index, dict)

    @patch("sweepai.core.vector_db.init_deeplake_vs")
    def test_compute_deeplake_vs(self, mock_init_deeplake_vs):
        collection_name = "repo_name"
        documents = ["doc1", "doc2", "doc3"]
        ids = ["id1", "id2", "id3"]
        metadatas = [{"file_path": "file1", "start": 0, "end": 10, "score": 1}, {"file_path": "file2", "start": 0, "end": 10, "score": 2}, {"file_path": "file3", "start": 0, "end": 10, "score": 3}]
        sha = "abc123"
        mock_init_deeplake_vs.return_value = MagicMock()
        vs = compute_deeplake_vs(collection_name, documents, ids, metadatas, sha)
        self.assertIsInstance(vs, VectorStore)

    @patch("sweepai.core.vector_db.SentenceTransformer")
    def test_compute_embeddings(self, mock_sentence_transformer):
        documents = ["doc1", "doc2", "doc3"]
        mock_sentence_transformer.return_value.encode.return_value = [1, 2, 3]
        embeddings, documents_to_compute, computed_embeddings, embedding = compute_embeddings(documents)
        self.assertEqual(embeddings.tolist(), [[1, 2, 3], [1, 2, 3], [1, 2, 3]])
        self.assertEqual(documents_to_compute, [])
        self.assertEqual(computed_embeddings, [])
        self.assertEqual(embedding, None)

    @patch("sweepai.core.vector_db.get_deeplake_vs_from_repo")
    @patch("sweepai.core.vector_db.search_index")
    @patch("sweepai.core.vector_db.SentenceTransformer")
    def test_get_relevant_snippets(self, mock_sentence_transformer, mock_search_index, mock_get_deeplake_vs_from_repo):
        mock_cloned_repo = MagicMock()
        mock_cloned_repo.repo_full_name = "repo_name"
        mock_cloned_repo.installation_id = "123"
        query = "query"
        username = "username"
        sweep_config = SweepConfig()
        mock_sentence_transformer.return_value.encode.return_value = [1, 2, 3]
        mock_get_deeplake_vs_from_repo.return_value = (MagicMock(), {}, 0)
        mock_search_index.return_value = {}
        snippets = get_relevant_snippets(mock_cloned_repo, query, username, sweep_config)
        self.assertEqual(snippets, [])


if __name__ == "__main__":
    unittest.main()
