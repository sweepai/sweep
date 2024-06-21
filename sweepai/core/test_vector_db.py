import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from sweepai.core.vector_db import (
    embed_text_array,
    openai_call_embedding,
    apply_adjustment_score,
    get_pointwise_reranked_snippet_scores,
    Snippet,
)

# Mock Redis client
@pytest.fixture
def mock_redis_client():
    with patch('sweepai.core.vector_db.redis_client') as mock_client:
        yield mock_client

# Mock OpenAI client
@pytest.fixture
def mock_openai_client():
    with patch('sweepai.core.vector_db.openai_client') as mock_client:
        yield mock_client

# Test data
@pytest.fixture
def sample_texts():
    return ["Hello, world!", "This is a test.", "Vector embeddings are cool."]

@pytest.fixture
def sample_snippets():
    return [
        Snippet(file_path="file1.py", start=1, end=5, content="def function1():"),
        Snippet(file_path="file2.py", start=10, end=15, content="class MyClass:"),
    ]

# Tests for embed_text_array function
def test_embed_text_array(mock_redis_client, mock_openai_client, sample_texts):
    mock_openai_client.embeddings.create.return_value.data = [
        MagicMock(embedding=np.random.rand(512)) for _ in range(len(sample_texts))
    ]
    
    result = embed_text_array(sample_texts)
    
    assert len(result) == 1  # Since BATCH_SIZE is not reached
    assert isinstance(result[0], np.ndarray)
    assert result[0].shape[0] == len(sample_texts)
    assert result[0].shape[1] == 512  # Assuming 512-dimensional embeddings

# Tests for openai_call_embedding function
def test_openai_call_embedding(mock_openai_client, sample_texts):
    mock_openai_client.embeddings.create.return_value.data = [
        MagicMock(embedding=np.random.rand(1024)) for _ in range(len(sample_texts))
    ]
    
    result = openai_call_embedding(sample_texts)
    
    assert isinstance(result, np.ndarray)
    assert result.shape == (len(sample_texts), 512)  # Check if dimensions are reduced to 512

def test_openai_call_embedding_error_handling(mock_openai_client):
    mock_openai_client.embeddings.create.side_effect = Exception("API Error")
    
    with pytest.raises(Exception):
        openai_call_embedding(["Test text"])

# Tests for apply_adjustment_score function
@pytest.mark.parametrize("file_path, old_score, expected", [
    ("test_file.py", 0.8, 0.8),
    ("test_file_123.py", 0.8, 0.8 * (1 - 1/14)**3),
    ("v1.2.3/test.py", 0.8, 0.8 * (1 - 1/9)**5),
])
def test_apply_adjustment_score(file_path, old_score, expected):
    result = apply_adjustment_score(file_path, old_score)
    assert pytest.approx(result, 0.001) == expected

# Tests for get_pointwise_reranked_snippet_scores function
def test_get_pointwise_reranked_snippet_scores(sample_snippets, mock_redis_client):
    query = "Test query"
    snippet_scores = {snippet.denotation: 0.5 for snippet in sample_snippets}
    
    with patch('sweepai.core.vector_db.cohere_rerank_call') as mock_cohere:
        mock_cohere.return_value.results = [
            MagicMock(index=i, relevance_score=0.7) for i in range(len(sample_snippets))
        ]
        
        result = get_pointwise_reranked_snippet_scores(query, sample_snippets, snippet_scores)
    
    assert isinstance(result, dict)
    assert len(result) == len(sample_snippets)
    for score in result.values():
        assert 0 <= score <= 1

if __name__ == "__main__":
    pytest.main()