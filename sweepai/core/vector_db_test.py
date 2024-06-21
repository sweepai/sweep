import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from sweepai.core.vector_db import (
    cosine_similarity,
    embed_text_array,
    openai_call_embedding,
    openai_with_expo_backoff,
    normalize_l2,
)
from sweepai.config.server import CACHE_DIRECTORY

# Mock the Cache class
@pytest.fixture
def mock_cache():
    with patch('sweepai.core.vector_db.Cache') as mock:
        yield mock

# Mock the openai client
@pytest.fixture
def mock_openai_client():
    with patch('sweepai.core.vector_db.get_embeddings_client') as mock:
        yield mock

def test_embed_text_array(mock_openai_client):
    mock_openai_client.return_value.embeddings.create.return_value.data = [
        MagicMock(embedding=list(range(512))) for _ in range(2)
    ]
    
    texts = ["Hello, world!", "Test embedding"]
    result = embed_text_array(texts)
    
    assert len(result) == 1  # One batch
    assert result[0].shape == (2, 512)  # Two embeddings, 512 dimensions each
    mock_openai_client.return_value.embeddings.create.assert_called_once()

def test_normalize_l2():
    x = np.array([3, 4])
    normalized = normalize_l2(x)
    assert np.allclose(normalized, np.array([0.6, 0.8]))

    X = np.array([[3, 4], [6, 8]])
    normalized = normalize_l2(X)
    expected = np.array([[0.6, 0.8], [0.6, 0.8]])
    assert np.allclose(normalized, expected)

def test_cosine_similarity():
    a = np.array([[1, 0]])
    B = np.array([[1, 0], [0, 1], [1, 1]])
    result = cosine_similarity(a, B)
    expected = np.array([[1, 0, 1/np.sqrt(2)]])
    assert np.allclose(result, expected)

def test_openai_with_expo_backoff(mock_cache):
    mock_cache.return_value.get.side_effect = [None, np.array([1, 2, 3])]
    mock_cache.return_value.set = MagicMock()

    with patch('sweepai.core.vector_db.openai_call_embedding', return_value=np.array([[4, 5, 6]])):
        result = openai_with_expo_backoff(["uncached text", "cached text"])

    assert np.array_equal(result, np.array([[4, 5, 6], [1, 2, 3]]))
    mock_cache.return_value.set.assert_called_once()

def test_openai_call_embedding_token_limit():
    long_text = "a" * 10000  # Assuming this exceeds the token limit
    with patch('sweepai.core.vector_db.tiktoken_client.count', return_value=10000):
        with patch('sweepai.core.vector_db.tiktoken_client.truncate_string', return_value="truncated"):
            with patch('sweepai.core.vector_db.openai_call_embedding_router', side_effect=[
                openai.BadRequestError("maximum context length"),
                np.array([[1, 2, 3]])
            ]) as mock_router:
                result = openai_call_embedding([long_text])
                
                assert np.array_equal(result, np.array([[1, 2, 3]]))
                assert mock_router.call_count == 2
                mock_router.assert_called_with(["truncated"], "document")

@pytest.mark.parametrize("exception,expected_calls", [
    (requests.exceptions.Timeout(), 5),
    (Exception("Unknown error"), 1)
])
def test_openai_with_expo_backoff_retries(exception, expected_calls):
    with patch('sweepai.core.vector_db.openai_call_embedding', side_effect=exception):
        with pytest.raises(Exception):
            openai_with_expo_backoff(["test"])
        assert openai_call_embedding.call_count == expected_calls