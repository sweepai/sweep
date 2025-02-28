import pytest
import numpy as np
from sweepai.core.vector_db import (
    embed_text_array,
    openai_call_embedding,
    multi_get_query_texts_similarity,
    cosine_similarity,
    normalize_l2,
)
from sweepai.utils.hash import hash_sha256
from sweepai.config.server import CACHE_VERSION

# Mock the openai and redis clients
import unittest.mock

@pytest.fixture
def mock_openai():
    with unittest.mock.patch('sweepai.core.vector_db.openai') as mock:
        yield mock

@pytest.fixture
def mock_redis():
    with unittest.mock.patch('sweepai.core.vector_db.vector_cache') as mock:
        yield mock
def test_embed_text_array(mock_openai, mock_redis):
    mock_openai.Embedding.create.return_value = {
        'data': [{'embedding': [0.1, 0.2, 0.3]} for _ in range(3)]
    }
    mock_redis.get.return_value = None

    texts = ['Hello', 'World', 'Test']
    result = embed_text_array(texts)

    assert len(result) == 1
    assert result[0].shape == (3, 3)
    mock_openai.Embedding.create.assert_called_once()
    assert mock_redis.set.call_count == 3

def test_openai_call_embedding(mock_openai):
    mock_openai.Embedding.create.return_value = {
        'data': [{'embedding': [0.1, 0.2, 0.3]} for _ in range(2)]
    }

    batch = ['Test1', 'Test2']
    result = openai_call_embedding(batch)

    assert result.shape == (2, 3)
    mock_openai.Embedding.create.assert_called_once_with(
        input=batch, model="text-embedding-ada-002"
    )
def test_caching(mock_redis):
    text = "Test text"
    cache_key = hash_sha256(text) + CACHE_VERSION
    cached_embedding = [0.1, 0.2, 0.3]
    mock_redis.get.return_value = str(cached_embedding)

    with unittest.mock.patch('sweepai.core.vector_db.openai_call_embedding') as mock_openai:
        embed_text_array([text])
        mock_openai.assert_not_called()

    mock_redis.get.assert_called_once_with(cache_key)
def test_multi_get_query_texts_similarity():
    queries = ["query1", "query2"]
    documents = ["doc1", "doc2", "doc3"]
    
    with unittest.mock.patch('sweepai.core.vector_db.embed_text_array') as mock_embed:
        mock_embed.return_value = [np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]])]
        with unittest.mock.patch('sweepai.core.vector_db.openai_call_embedding') as mock_openai:
            mock_openai.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
            
            result = multi_get_query_texts_similarity(queries, documents)
            
            assert len(result) == 2
            assert len(result[0]) == 3
            assert all(isinstance(score, float) for score in result[0])

def test_cosine_similarity():
    a = np.array([[1, 0, 0]])
    B = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    result = cosine_similarity(a, B)
    expected = np.array([[1, 0, 0]])
    np.testing.assert_array_almost_equal(result, expected)

def test_normalize_l2():
    x = np.array([3, 4])
    result = normalize_l2(x)
    expected = np.array([0.6, 0.8])
    np.testing.assert_array_almost_equal(result, expected)

    x = np.array([[1, 2], [3, 4]])
    result = normalize_l2(x)
    expected = np.array([[0.4472136, 0.89442719], [0.6, 0.8]])
    np.testing.assert_array_almost_equal(result, expected)