import unittest
from unittest.mock import patch, MagicMock
import numpy as np
from sweepai.core.vector_db import (
    embed_text_array,
    openai_call_embedding,
    apply_adjustment_score,
    get_pointwise_reranked_snippet_scores,
    Snippet,
)

class TestVectorDB(unittest.TestCase):
    def setUp(self):
        self.texts = ["Hello, world!", "This is a test.", "Vector embeddings are cool."]
        self.mock_embedding = np.array([0.1, 0.2, 0.3])

    @patch('sweepai.core.vector_db.openai_with_expo_backoff')
    def test_embed_text_array(self, mock_openai):
        mock_openai.return_value = np.array([self.mock_embedding] * len(self.texts))
        
        result = embed_text_array(self.texts)
        
        self.assertEqual(len(result), 1)  # Since BATCH_SIZE is not reached
        self.assertTrue(np.array_equal(result[0], np.array([self.mock_embedding] * len(self.texts))))
        mock_openai.assert_called_once_with(self.texts)patch('sweepai.core.vector_db.get_embeddings_client')
    def test_openai_call_embedding(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.embeddings.create.return_value.data = [
            MagicMock(embedding=self.mock_embedding.tolist()) for _ in self.texts
        ]

        result = openai_call_embedding(self.texts)

        self.assertTrue(np.array_equal(result, np.array([self.mock_embedding] * len(self.texts))))
        mock_client.embeddings.create.assert_called_once_with(
            input=self.texts, model="text-embedding-3-small", encoding_format="float"
        )

    def test_apply_adjustment_score(self):
        test_cases = [
            ("path/to/file.py", 1.0, 1.0),
            ("path/to/file1.py", 1.0, 0.9),
            ("path/to/file123.py", 1.0, 0.7),
        ]

        for path, score, expected in test_cases:
            with self.subTest(path=path):
                result = apply_adjustment_score(path, score)
                self.assertAlmostEqual(result, expected, places=1)

    @patch('sweepai.core.vector_db.cohere_rerank_call')
    def test_get_pointwise_reranked_snippet_scores(self, mock_cohere):
        query = "test query"
        snippets = [
            Snippet("file1.py", 1, 10, "content1"),
            Snippet("file2.py", 1, 10, "content2"),
        ]
        snippet_scores = {
            "file1.py:1:10": 0.8,
            "file2.py:1:10": 0.6,
        }

        mock_cohere.return_value = MagicMock(
            results=[
                MagicMock(index=0, relevance_score=0.9),
                MagicMock(index=1, relevance_score=0.7),
            ]
        )

        result = get_pointwise_reranked_snippet_scores(query, snippets, snippet_scores)

        self.assertAlmostEqual(result["file1.py:1:10"], 0.9, places=1)
        self.assertAlmostEqual(result["file2.py:1:10"], 0.7, places=1)
        mock_cohere.assert_called_once()

if __name__ == '__main__':
    unittest.main()