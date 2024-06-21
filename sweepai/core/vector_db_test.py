import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from sweepai.core.vector_db import (
    cosine_similarity,
    chunk,
    multi_get_query_texts_similarity,
    normalize_l2,
    embed_text_array,
    openai_call_embedding,
)

@pytest.fixture
def mock_openai_client():
    with patch("sweepai.core.vector_db.get_embeddings_client") as mock_client:
        yield mock_client

@pytest.fixture
def mock_redis_client():
    with patch("sweepai.core.vector_db.Cache") as mock_cache:
        yield mock_cache.return_valuedef test_cosine_similarity():
    a = np.array([[1, 0, 1]])
    B = np.array([[1, 0, 1], [0, 1, 0], [1, 1, 1]])
    result = cosine_similarity(a, B)
    expected = np.array([[1.0, 0.0, 0.8164966]])
    np.testing.assert_array_almost_equal(result, expected, decimal=6)def test_chunk():
    texts = ["text1", "text2", "text3", "text4", "text5"]
    batch_size = 2
    result = list(chunk(texts, batch_size))
    expected = [["text1", "text2"], ["text3", "text4"], ["text5"]]
    assert result == expecteddef test_normalize_l2():
    x = np.array([[3, 4], [6, 8]])
    result = normalize_l2(x)
    expected = np.array([[0.6, 0.8], [0.6, 0.8]])
    np.testing.assert_array_almost_equal(result, expected, decimal=6)def test_embed_text_array(mock_openai_client):
    texts = ["Hello, world!", "This is a test."]
    mock_embeddings = [
        np.array([0.1, 0.2, 0.3]),
        np.array([0.4, 0.5, 0.6])
    ]
    mock_openai_client.return_value.embeddings.create.return_value.data = [
        MagicMock(embedding=emb) for emb in mock_embeddings
    ]

    result = embed_text_array(texts)
    expected = np.array(mock_embeddings)
    np.testing.assert_array_almost_equal(result, expected, decimal=6)

    mock_openai_client.return_value.embeddings.create.assert_called_once_with(
        input=texts, model="text-embedding-3-small", encoding_format="float"
    )def test_openai_call_embedding_with_cache(mock_redis_client, mock_openai_client):
    batch = ["Hello, world!", "This is a test."]
    cache_keys = ["hash1", "hash2"]
    mock_embeddings = [
        np.array([0.1, 0.2, 0.3]),
        np.array([0.4, 0.5, 0.6])
    ]

    # Simulate cache hit for the first item and cache miss for the second
    mock_redis_client.get.side_effect = [json.dumps(mock_embeddings[0].tolist()), None]
    
    mock_openai_client.return_value.embeddings.create.return_value.data = [
        MagicMock(embedding=mock_embeddings[1])
    ]

    with patch("sweepai.core.vector_db.hash_sha256", side_effect=cache_keys):
        result = openai_call_embedding(batch)

    expected = np.array(mock_embeddings)
    np.testing.assert_array_almost_equal(result, expected, decimal=6)

    # Check if cache was used for the first item and OpenAI was called for the second
    mock_redis_client.get.assert_called_with(cache_keys[1] + CACHE_VERSION)
    mock_openai_client.return_value.embeddings.create.assert_called_once_with(
        input=[batch[1]], model="text-embedding-3-small", encoding_format="float"
    )
    mock_redis_client.set.assert_called_once()