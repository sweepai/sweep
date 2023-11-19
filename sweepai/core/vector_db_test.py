import unittest
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import numpy as np

from sweepai.core.sweep_config import SweepConfig
from sweepai.core.vector_db import (chunk, compute_deeplake_vs,
                                    compute_embeddings,
                                    compute_vector_search_scores,
                                    embed_huggingface, embed_replicate,
                                    embed_texts, get_deeplake_vs_from_repo,
                                    get_relevant_snippets,
                                    prepare_documents_metadata_ids)


class TestVectorDbComputeDeeplakeVs(unittest.TestCase):
    @patch("sweepai.core.vector_db.redis_client")
    @patch("sweepai.core.vector_db.embedding_function")
    @patch("sweepai.core.vector_db.init_deeplake_vs")
    def test_compute_deeplake_vs(self, mock_init_deeplake_vs, mock_embedding_function, mock_redis_client):
        # Arrange
        collection_name = "test_collection"
        documents = ["doc1", "doc2"]
        ids = ["id1", "id2"]
        metadatas = ["meta1", "meta2"]
        sha = "123456"

        mock_redis_client.mget.return_value = [None] * len(documents)
        mock_redis_client.mset.return_value = None

        mock_embedding_function.return_value = [np.array([1.0, 2.0])] * len(documents)

        mock_init_deeplake_vs.return_value = MagicMock()

        # Act
        result = compute_deeplake_vs(collection_name, documents, ids, metadatas, sha)

        # Assert
        mock_redis_client.mget.assert_called_once()
        mock_redis_client.mset.assert_called_once()
        mock_embedding_function.assert_called_once_with(documents)
        mock_init_deeplake_vs.assert_called_once_with(collection_name)
        self.assertIsNotNone(result)



    @patch("sweepai.core.vector_db.redis_client")
    @patch("sweepai.core.vector_db.embedding_function")
    @patch("sweepai.core.vector_db.init_deeplake_vs")
    def test_compute_deeplake_vs_with_empty_documents(self, mock_init_deeplake_vs, mock_embedding_function, mock_redis_client):
        # Arrange
        collection_name = "test_collection"
        documents = []
        ids = ["id1", "id2"]
        metadatas = ["meta1", "meta2"]
        sha = "123456"

        mock_redis_client.mget.return_value = [None] * len(documents)
        mock_redis_client.mset.return_value = None

        mock_embedding_function.return_value = [np.array([1.0, 2.0])] * len(documents)

        mock_init_deeplake_vs.return_value = MagicMock()

        # Act
        result = compute_deeplake_vs(collection_name, documents, ids, metadatas, sha)

        # Assert
        mock_redis_client.mget.assert_not_called()
        mock_redis_client.mset.assert_not_called()
        mock_embedding_function.assert_not_called()
        mock_init_deeplake_vs.assert_not_called()
        self.assertIsNone(result)
class TestVectorDBPrepareDocumentsMetadataIds(unittest.TestCase):
    def setUp(self):
        self.mock_snippet = MagicMock()
        self.mock_snippet.get_snippet.return_value = "mock snippet"
        self.mock_snippet.file_path = "mock file path"
        self.mock_snippet.start = 1
        self.mock_snippet.end = 2

        self.mock_cloned_repo = MagicMock()
        self.mock_cloned_repo.cached_dir = "mock cached dir"

        self.mock_files_to_scores = {"mock file path": 0.5}

    @patch("sweepai.core.vector_db.parse_collection_name")
    def test_prepare_documents_metadata_ids(self, mock_parse_collection_name):
        mock_parse_collection_name.return_value = "mock collection name"
        snippets = [self.mock_snippet]
        cloned_repo = self.mock_cloned_repo
        files_to_scores = self.mock_files_to_scores
        start = 0
        repo_full_name = "mock/repo"

        result = prepare_documents_metadata_ids(
            snippets, cloned_repo, files_to_scores, start, repo_full_name
        )

        self.assertEqual(result[0], "mock collection name")
        self.assertEqual(result[1], ["mock snippet"])
        self.assertEqual(result[2], ["mock file path:1:2"])
        self.assertEqual(result[3], [{"file_path": "mock file path", "start": 1, "end": 2, "score": 0.5}])



    @patch("sweepai.core.vector_db.parse_collection_name")
    @patch("sweepai.core.vector_db.logger")
    @patch("time.time")
    def test_prepare_documents_metadata_ids_empty_snippets(self, mock_time, mock_logger, mock_parse_collection_name):
        mock_parse_collection_name.return_value = "mock collection name"
        mock_time.return_value = 0
        snippets = []
        cloned_repo = self.mock_cloned_repo
        files_to_scores = self.mock_files_to_scores
        start = 0
        repo_full_name = "mock/repo"

        result = prepare_documents_metadata_ids(
            snippets, cloned_repo, files_to_scores, start, repo_full_name
        )

        self.assertEqual(result[0], "mock collection name")
        self.assertEqual(result[1], [])
        self.assertEqual(result[2], [])
        self.assertEqual(result[3], [])
class TestEmbedTextsEmbedTexts(unittest.TestCase):
    @patch("sweepai.core.vector_db.SentenceTransformer")
    @patch("sweepai.core.vector_db.openai.Embedding.create")
    @patch("sweepai.core.vector_db.embed_huggingface")
    @patch("sweepai.core.vector_db.embed_replicate")
    def test_embed_texts(self, mock_embed_replicate, mock_embed_huggingface, mock_openai_embedding, mock_sentence_transformer):
        mock_sentence_transformer.return_value.encode.return_value = "mocked embedding"
        mock_openai_embedding.return_value = {"data": [{"embedding": "mocked embedding"}]}
        mock_embed_huggingface.return_value = "mocked embedding"
        mock_embed_replicate.return_value = "mocked embedding"

        # Test for each VECTOR_EMBEDDING_SOURCE
        VECTOR_EMBEDDING_SOURCE = ["sentence-transformers", "openai", "huggingface", "replicate", "none"]
        for source in VECTOR_EMBEDDING_SOURCE:
            result = embed_texts(("test text",), source)
            self.assertEqual(result, "mocked embedding")


    @patch("sweepai.core.vector_db.SentenceTransformer")
    @patch("sweepai.core.vector_db.openai.Embedding.create")
    @patch("sweepai.core.vector_db.embed_huggingface")
    @patch("sweepai.core.vector_db.embed_replicate")
    @patch("sweepai.core.vector_db.VECTOR_EMBEDDING_SOURCE")
    def test_embed_texts_empty_tuple(self, mock_vector_embedding_source, mock_embed_replicate, mock_embed_huggingface, mock_openai_embedding, mock_sentence_transformer):
        mock_sentence_transformer.return_value.encode.return_value = "mocked embedding"
        mock_openai_embedding.return_value = {"data": [{"embedding": "mocked embedding"}]}
        mock_embed_huggingface.return_value = "mocked embedding"
        mock_embed_replicate.return_value = "mocked embedding"

        # Test for each VECTOR_EMBEDDING_SOURCE
        VECTOR_EMBEDDING_SOURCE = ["sentence-transformers", "openai", "huggingface", "replicate", "none"]
        for source in VECTOR_EMBEDDING_SOURCE:
            mock_vector_embedding_source.return_value = source
            result = embed_texts(())
            self.assertEqual(result, [])
class TestEmbedReplicateEmbedReplicate(unittest.TestCase):
    @patch("replicate.Client")
    def test_embed_replicate(self, mock_client):
        mock_deployment = MagicMock()
        mock_prediction = MagicMock()

        type(mock_client.return_value).deployments = PropertyMock(return_value=mock_deployment)
        type(mock_deployment).predictions = PropertyMock(return_value=mock_prediction)
        type(mock_prediction).output = PropertyMock(return_value=[{"embedding": "mock_embedding"}])

        result = embed_replicate(["test text"])
        self.assertEqual(result, ["mock_embedding"])


    @patch("sweepai.core.vector_db.REPLICATE_API_KEY", "mock_api_key")
    @patch("sweepai.core.vector_db.REPLICATE_DEPLOYMENT_URL", "mock_deployment_url")
    @patch("sweepai.core.vector_db.logger.exception")
    @patch("replicate.Client")
    def test_embed_replicate_empty_texts(self, mock_client, mock_logger_exception):
        mock_deployment = MagicMock()
        mock_prediction = MagicMock()

        type(mock_client.return_value).deployments = PropertyMock(return_value=mock_deployment)
        type(mock_deployment).predictions = PropertyMock(return_value=mock_prediction)
        type(mock_prediction).output = PropertyMock(return_value=[])

        result = embed_replicate([])
        self.assertEqual(result, [])
class TestVectorDBComputeVectorSearchScores(unittest.TestCase):
    @patch("sweepai.core.vector_db.compute_score")
    @patch("sweepai.core.vector_db.get_scores")
    @patch("sweepai.core.vector_db.redis_client")
    @patch("sweepai.core.vector_db.logger")
    def test_compute_vector_search_scores(self, mock_logger, mock_redis_client, mock_get_scores, mock_compute_score):
        mock_compute_score.return_value = 0.5
        mock_get_scores.return_value = [0.5, 0.5, 0.5]
        mock_redis_client.get.return_value = None
        mock_redis_client.set.return_value = None
        mock_logger.exception.return_value = None
        mock_logger.info.return_value = None

        cloned_repo = MagicMock()
        cloned_repo.cached_dir = "/path/to/cached_dir"
        cloned_repo.git_repo = MagicMock()

        file_list = ["/path/to/cached_dir/file1", "/path/to/cached_dir/file2", "/path/to/cached_dir/file3"]
        repo_full_name = "test/repo"

        result = compute_vector_search_scores(file_list, cloned_repo, repo_full_name)

        self.assertEqual(result, {file: 0.5 for file in file_list})


    @patch("sweepai.core.vector_db.compute_score")
    @patch("sweepai.core.vector_db.get_scores")
    @patch("sweepai.core.vector_db.redis_client")
    @patch("sweepai.core.vector_db.logger")
    def test_compute_vector_search_scores_empty_file_list(self, mock_logger, mock_redis_client, mock_get_scores, mock_compute_score):
        mock_compute_score.return_value = 0.5
        mock_get_scores.return_value = []
        mock_redis_client.get.return_value = None
        mock_redis_client.set.return_value = None
        mock_logger.exception.return_value = None
        mock_logger.info.return_value = None

        cloned_repo = MagicMock()
        cloned_repo.cached_dir = "/path/to/cached_dir"
        cloned_repo.git_repo = MagicMock()

        file_list = []
        repo_full_name = "test/repo"

        result = compute_vector_search_scores(file_list, cloned_repo, repo_full_name)

        self.assertEqual(result, {})
class TestVectorDbEmbedHuggingface(unittest.TestCase):
    @patch("requests.post")
    def test_embed_huggingface(self, mock_requests_post):
        # Arrange
        mock_response_json = MagicMock()
        mock_response_json.return_value = {"embeddings": "mock embeddings"}
        mock_requests_post.return_value.json = mock_response_json
        texts = ["test text"]

        # Act
        result = embed_huggingface(texts)

        # Assert
        self.assertEqual(result, "mock embeddings")
        mock_requests_post.assert_called_once_with(
            HUGGINGFACE_URL, 
            headers={
                "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
                "Content-Type": "application/json",
            }, 
            json={"inputs": texts}
        )


    @patch("sweepai.core.vector_db.HUGGINGFACE_TOKEN", "mock_token")
    @patch("sweepai.core.vector_db.HUGGINGFACE_URL", "mock_url")
    @patch("requests.post")
    def test_embed_huggingface_empty_texts(self, mock_requests_post):
        # Arrange
        mock_response_json = MagicMock()
        mock_response_json.return_value = {"embeddings": "mock embeddings"}
        mock_requests_post.return_value.json = mock_response_json
        texts = []

        # Act
        result = embed_huggingface(texts)

        # Assert
        self.assertEqual(result, "mock embeddings")
        mock_requests_post.assert_called_once_with(
            "mock_url", 
            headers={
                "Authorization": f"Bearer mock_token",
                "Content-Type": "application/json",
            }, 
            json={"inputs": texts}
        )
class TestVectorDBGetDeeplakeVsFromRepo(unittest.TestCase):
    @patch("sweepai.core.vector_db.get_blocked_dirs")
    @patch("sweepai.core.vector_db.prepare_lexical_search_index")
    @patch("sweepai.core.vector_db.compute_vector_search_scores")
    @patch("sweepai.core.vector_db.prepare_documents_metadata_ids")
    @patch("sweepai.core.vector_db.compute_deeplake_vs")
    def test_get_deeplake_vs_from_repo(self, mock_compute_deeplake_vs, mock_prepare_documents_metadata_ids, mock_compute_vector_search_scores, mock_prepare_lexical_search_index, mock_get_blocked_dirs):
        mock_cloned_repo = MagicMock()
        mock_cloned_repo.repo_full_name = "mock_repo_full_name"
        mock_cloned_repo.repo = MagicMock()
        mock_cloned_repo.repo.get_commits.return_value = [Mock(sha="mock_sha")]

        mock_get_blocked_dirs.return_value = []
        mock_prepare_lexical_search_index.return_value = ("mock_file_list", "mock_snippets", "mock_index")
        mock_compute_vector_search_scores.return_value = "mock_files_to_scores"
        mock_prepare_documents_metadata_ids.return_value = ("mock_collection_name", "mock_documents", "mock_ids", "mock_metadatas")
        mock_compute_deeplake_vs.return_value = "mock_deeplake_vs"

        result = get_deeplake_vs_from_repo(mock_cloned_repo, SweepConfig())

        self.assertEqual(result, ("mock_deeplake_vs", "mock_index", len("mock_documents")))



    @patch("sweepai.core.vector_db.get_blocked_dirs")
    @patch("sweepai.core.vector_db.prepare_lexical_search_index")
    @patch("sweepai.core.vector_db.compute_vector_search_scores")
    @patch("sweepai.core.vector_db.prepare_documents_metadata_ids")
    @patch("sweepai.core.vector_db.compute_deeplake_vs")
    def test_get_deeplake_vs_from_repo_no_commits(self, mock_compute_deeplake_vs, mock_prepare_documents_metadata_ids, mock_compute_vector_search_scores, mock_prepare_lexical_search_index, mock_get_blocked_dirs):
        mock_cloned_repo = MagicMock()
        mock_cloned_repo.repo_full_name = "mock_repo_full_name"
        mock_cloned_repo.repo = MagicMock()
        mock_cloned_repo.repo.get_commits.return_value = []

        mock_get_blocked_dirs.return_value = []
        mock_prepare_lexical_search_index.return_value = ("mock_file_list", "mock_snippets", "mock_index")
        mock_compute_vector_search_scores.return_value = "mock_files_to_scores"
        mock_prepare_documents_metadata_ids.return_value = ("mock_collection_name", "mock_documents", "mock_ids", "mock_metadatas")
        mock_compute_deeplake_vs.return_value = "mock_deeplake_vs"

        result = get_deeplake_vs_from_repo(mock_cloned_repo, SweepConfig())

        self.assertEqual(result, ("mock_deeplake_vs", "mock_index", len("mock_documents")))
class TestVectorDBComputeEmbeddings(unittest.TestCase):
    @patch("sweepai.core.vector_db.redis_client")
    @patch("sweepai.core.vector_db.embedding_function")
    @patch("sweepai.core.vector_db.convert_to_numpy_array")
    def test_compute_embeddings(self, mock_convert_to_numpy_array, mock_embedding_function, mock_redis_client):
        # Arrange
        documents = ["doc1", "doc2"]
        mock_redis_client.mget.return_value = [None, None]
        mock_embedding_function.return_value = ["embed1", "embed2"]
        mock_convert_to_numpy_array.return_value = ["numpy1", "numpy2"]

        # Act
        result = compute_embeddings(documents)

        # Assert
        self.assertEqual(result, (["numpy1", "numpy2"], documents, ["embed1", "embed2"], "embed2"))
        mock_redis_client.mget.assert_called_once_with(["doc1", "doc2"])
        mock_embedding_function.assert_called_once_with(documents)
        mock_convert_to_numpy_array.assert_called_once_with(["embed1", "embed2"], documents)



    @patch("sweepai.core.vector_db.redis_client")
    @patch("sweepai.core.vector_db.embedding_function")
    @patch("sweepai.core.vector_db.convert_to_numpy_array")
    def test_compute_embeddings_empty_documents(self, mock_convert_to_numpy_array, mock_embedding_function, mock_redis_client):
        # Arrange
        documents = []

        # Act
        result = compute_embeddings(documents)

        # Assert
        self.assertEqual(result, ([], [], [], None))
        mock_redis_client.mget.assert_not_called()
        mock_embedding_function.assert_not_called()
        mock_convert_to_numpy_array.assert_not_called()
class TestGetRelevantSnippetsGetRelevantSnippets(unittest.TestCase):
    @patch("sweepai.core.vector_db.embedding_function")
    @patch("sweepai.core.vector_db.get_deeplake_vs_from_repo")
    @patch("sweepai.core.vector_db.search_index")
    @patch("sweepai.core.vector_db.posthog.capture")
    @patch("sweepai.core.vector_db.deeplake_vs.search")
    def test_get_relevant_snippets(self, mock_embedding_function, mock_get_deeplake_vs_from_repo, mock_search_index, mock_posthog_capture, mock_deeplake_vs_search):
        # Arrange
        mock_embedding_function.return_value = MagicMock()
        mock_get_deeplake_vs_from_repo.return_value = (MagicMock(), MagicMock(), 10)
        mock_search_index.return_value = MagicMock()
        mock_posthog_capture.return_value = MagicMock()
        mock_deeplake_vs_search.return_value = {"metadata": [], "text": []}

        # Act
        result = get_relevant_snippets(MagicMock(), "query")

        # Assert
        self.assertEqual(result, [])


    @patch("sweepai.core.vector_db.embedding_function")
    @patch("sweepai.core.vector_db.get_deeplake_vs_from_repo")
    @patch("sweepai.core.vector_db.search_index")
    @patch("sweepai.core.vector_db.posthog.capture")
    @patch("sweepai.core.vector_db.deeplake_vs.search")
    def test_get_relevant_snippets_embedding_function_exception(self, mock_embedding_function, mock_get_deeplake_vs_from_repo, mock_search_index, mock_posthog_capture, mock_deeplake_vs_search):
        # Arrange
        mock_embedding_function.side_effect = Exception("Test exception")
        mock_get_deeplake_vs_from_repo.return_value = (MagicMock(), MagicMock(), 10)
        mock_search_index.return_value = MagicMock()
        mock_posthog_capture.return_value = MagicMock()
        mock_deeplake_vs_search.return_value = {"metadata": [], "text": []}

        # Act and Assert
        with self.assertRaises(Exception) as context:
            get_relevant_snippets(MagicMock(), "query")
        self.assertTrue("Test exception" in str(context.exception))
class TestChunkChunk(unittest.TestCase):
    def test_chunk(self):
        texts = ["text1", "text2", "text3", "text4", "text5"]
        batch_size = 2
        expected_output = [["text1", "text2"], ["text3", "text4"], ["text5"]]
        result = list(chunk(texts, batch_size))
        self.assertEqual(result, expected_output)

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

if __name__ == "__main__":
    unittest.main()
