import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from sweepai.core.vector_db import (
    embed_text_array,
    openai_call_embedding,
    multi_get_query_texts_similarity,
    cosine_similarity,
    normalize_l2,
)

@pytest.fixture
def mock_openai_embedding():
    with patch('sweepai.core.vector_db.openai_call_embedding') as mock:
        mock.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        yield mock

@pytest.fixture
def mock_redis_client():
    with patch('sweepai.core.vector_db.vector_cache') as mock:
        yield mock

def test_embed_text_array(mock_openai_embedding):
    texts = ["Hello, world!", "This is a test."]
    result = embed_text_array(texts)
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], np.ndarray)
    assert result[0].shape == (2, 3)
    mock_openai_embedding.assert_called_once_with(texts)

def test_openai_call_embedding():
    batch = ["Test text 1", "Test text 2"]
    result = openai_call_embedding(batch)
    assert isinstance(result, np.ndarray)
    assert result.shape[0] == len(batch)
    assert result.shape[1] == 512  # Assuming we're using the default 512 dimensions

def test_normalize_l2():
    x = np.array([3, 4])
    result = normalize_l2(x)
    assert np.allclose(result, np.array([0.6, 0.8]))

    x_2d = np.array([[3, 4], [6, 8]])
    result_2d = normalize_l2(x_2d)
    assert np.allclose(result_2d, np.array([[0.6, 0.8], [0.6, 0.8]]))

def test_embed_text_array_with_cache(mock_redis_client, mock_openai_embedding):
    texts = ["Cached text", "New text"]
    cached_embedding = np.array([0.7, 0.8, 0.9])
    mock_redis_client.get.side_effect = [cached_embedding.tobytes(), None]
    
    result = embed_text_array(texts)
    
    assert len(result) == 1
    assert np.allclose(result[0][0], cached_embedding)
    assert np.allclose(result[0][1], mock_openai_embedding.return_value[0])
    mock_openai_embedding.assert_called_once_with(["New text"])
    mock_redis_client.set.assert_called_once()

def test_cosine_similarity():
    a = np.array([[1, 0]])
    B = np.array([[1, 0], [0, 1], [-1, 0]])
    result = cosine_similarity(a, B)
    expected = np.array([[1, 0, -1]])
    assert np.allclose(result, expected)

def test_multi_get_query_texts_similarity(mock_openai_embedding):
    queries = ["Query 1", "Query 2"]
    documents = ["Doc 1", "Doc 2", "Doc 3"]
    mock_openai_embedding.side_effect = [
        np.array([[0.1, 0.2], [0.3, 0.4]]),  # Query embeddings
        np.array([[0.5, 0.6], [0.7, 0.8], [0.9, 1.0]])  # Document embeddings
    ]
    
    result = multi_get_query_texts_similarity(queries, documents)
    
    assert isinstance(result, list)
    assert len(result) == len(queries)
    assert len(result[0]) == len(documents)
    mock_openai_embedding.assert_called()