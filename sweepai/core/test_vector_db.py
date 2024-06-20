import pytest
import numpy as np
import mock
from sweepai.core.vector_db import (
    embed_text_array,
    openai_call_embedding,
    multi_get_query_texts_similarity,
    cosine_similarity,
    normalize_l2,
    vector_cache
)

def test_embed_text_array():
    texts = ["Hello, world!", "This is a test."]
    result = embed_text_array(texts)
    assert isinstance(result, list)
    assert len(result) == 1  # Since BATCH_SIZE is 512, this should be a single batch
    assert isinstance(result[0], np.ndarray)
    assert result[0].shape[0] == len(texts)

def test_openai_call_embedding():
    batch = ["Test embedding"]
    result = openai_call_embedding(batch)
    assert isinstance(result, np.ndarray)
    assert result.shape[0] == len(batch)
    assert result.shape[1] == 512  # Assuming we're using the 512-dimensional embeddings

def test_normalize_l2():
    x = np.array([3, 4])
    normalized = normalize_l2(x)
    assert np.allclose(normalized, np.array([0.6, 0.8]))

    x_2d = np.array([[3, 4], [6, 8]])
    normalized_2d = normalize_l2(x_2d)
    expected = np.array([[0.6, 0.8], [0.6, 0.8]])
    assert np.allclose(normalized_2d, expected)

@mock.patch('sweepai.core.vector_db.vector_cache')
def test_caching(mock_cache):
    mock_cache.get.return_value = None
    mock_cache.set.return_value = True

    texts = ["Cache test"]
    embed_text_array(texts)

    mock_cache.get.assert_called_once()
    mock_cache.set.assert_called_once()

def test_cosine_similarity():
    a = np.array([[1, 0]])
    B = np.array([[1, 0], [0, 1], [1, 1]])
    result = cosine_similarity(a, B)
    expected = np.array([[1, 0, 1/np.sqrt(2)]])
    assert np.allclose(result, expected)

def test_multi_get_query_texts_similarity():
    queries = ["test query"]
    documents = ["test document", "another document"]
    result = multi_get_query_texts_similarity(queries, documents)
    assert isinstance(result, list)
    assert len(result) == 1  # One query
    assert len(result[0]) == len(documents)  # Similarity score for each document

@mock.patch('sweepai.core.vector_db.openai_call_embedding')
def test_embed_text_array_with_mock(mock_openai):
    mock_embedding = np.random.rand(1, 512)
    mock_openai.return_value = mock_embedding

    texts = ["Mock test"]
    result = embed_text_array(texts)

    mock_openai.assert_called_once()
    assert np.array_equal(result[0], mock_embedding)

if __name__ == "__main__":
    pytest.main()