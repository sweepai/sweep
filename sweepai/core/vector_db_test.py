import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from sweepai.core.vector_db import (
    embed_text_array,
    openai_call_embedding,
    cosine_similarity,
    multi_get_query_texts_similarity,
    normalize_l2,
)
from sweepai.utils.hash import hash_sha25

# Mock the Cache class
@pytest.fixture
def mock_cache():
    with patch('sweepai.core.vector_db.Cache') as mock:
        yield mock.return_value

# Mock the openai client
@pytest.fixture
def mock_openai_client():
    with patch('sweepai.core.vector_db.get_embeddings_client') as mock:
        yield mock.return_value

def test_embed_text_array(mock_cache, mock_openai_client):
    texts = ["Hello, world!", "This is a test."]
    mock_embeddings = np.random.rand(2, 512)
    mock_openai_client.embeddings.create.return_value.data = [
        MagicMock(embedding=mock_embeddings[i]) for i in range(2)
    ]

    result = embed_text_array(texts)

    assert len(result) == 1
    assert result[0].shape == (2, 512)
    np.testing.assert_array_almost_equal(result[0], normalize_l2(mock_embeddings[:, :512]))

def test_openai_call_embedding(mock_openai_client):
    batch = ["Test sentence 1", "Test sentence 2"]
    mock_embeddings = np.random.rand(2, 1536)
    mock_openai_client.embeddings.create.return_value.data = [
        MagicMock(embedding=mock_embeddings[i]) for i in range(2)
    ]

    result = openai_call_embedding(batch)

    assert result.shape == (2, 512)
    np.testing.assert_array_almost_equal(result, normalize_l2(mock_embeddings[:, :512]))

def test_cosine_similarity():
    a = np.array([[1, 0, 0]])
    B = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    result = cosine_similarity(a, B)
    expected = np.array([[1, 0, 0]])
    np.testing.assert_array_almost_equal(result, expected)

def test_multi_get_query_texts_similarity(mock_openai_client):
    queries = ["Query 1", "Query 2"]
    documents = ["Document 1", "Document 2", "Document 3"]
    
    mock_query_embeddings = np.random.rand(2, 512)
    mock_doc_embeddings = np.random.rand(3, 512)
    
    mock_openai_client.embeddings.create.side_effect = [
        MagicMock(data=[MagicMock(embedding=e) for e in mock_query_embeddings]),
        MagicMock(data=[MagicMock(embedding=e) for e in mock_doc_embeddings])
    ]

    result = multi_get_query_texts_similarity(queries, documents)

    assert len(result) == 2
    assert len(result[0]) == 3
    assert all(0 <= sim <= 1 for sim in result[0])
    assert all(0 <= sim <= 1 for sim in result[1])

def test_caching(mock_cache, mock_openai_client):
    texts = ["Cached text", "New text"]
    cache_key = hash_sha256(texts[0]) + "v2.1.1"
    mock_cache_embedding = np.random.rand(512)
    mock_new_embedding = np.random.rand(512)

    mock_cache.get.side_effect = [mock_cache_embedding, None]
    mock_openai_client.embeddings.create.return_value.data = [
        MagicMock(embedding=mock_new_embedding)
    ]

    result = embed_text_array(texts)

    assert len(result) == 1
    assert result[0].shape == (2, 512)
    np.testing.assert_array_almost_equal(result[0][0], normalize_l2(mock_cache_embedding))
    np.testing.assert_array_almost_equal(result[0][1], normalize_l2(mock_new_embedding))

    mock_cache.set.assert_called_once_with(hash_sha256(texts[1]) + "v2.1.1", normalize_l2(mock_new_embedding))

def test_openai_call_embedding_error_handling(mock_openai_client):
    batch = ["Test sentence 1", "Test sentence 2"]
    mock_openai_client.embeddings.create.side_effect = [
        Exception("API Error"),
        MagicMock(data=[MagicMock(embedding=np.random.rand(512)) for _ in range(2)])
    ]

    with pytest.raises(Exception, match="API Error"):
        openai_call_embedding(batch)

    # Test truncation on BadRequestError
    mock_openai_client.embeddings.create.side_effect = [
        openai.BadRequestError("maximum context length"),
        MagicMock(data=[MagicMock(embedding=np.random.rand(512)) for _ in range(2)])
    ]

    result = openai_call_embedding(batch)
    assert result.shape == (2, 512)