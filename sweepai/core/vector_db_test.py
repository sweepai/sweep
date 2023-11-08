import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from sweepai.core import vector_db

def test_compute_embeddings():
    # Mock the embedding_function and convert_to_numpy functions
    with patch("sweepai.core.vector_db.embedding_function", return_value=[1, 2, 3]), \
         patch("sweepai.core.vector_db.convert_to_numpy", return_value=np.array([1, 2, 3])):
        # Test when embeddings can be successfully converted to a numpy array
        embeddings, documents_to_compute, computed_embeddings, embedding = vector_db.compute_embeddings(["doc1", "doc2"])
        assert np.array_equal(embeddings, np.array([1, 2, 3]))
        assert documents_to_compute == ["doc1", "doc2"]
        assert computed_embeddings == [1, 2, 3]
        assert embedding == 3

        # Test when an exception occurs during the conversion process
        vector_db.convert_to_numpy.side_effect = Exception("Failed to convert embeddings to numpy array")
        with pytest.raises(Exception, match="Failed to convert embeddings to numpy array"):
            vector_db.compute_embeddings(["doc1", "doc2"])

def test_convert_to_numpy():
    # Test when the list of embeddings can be successfully converted to a numpy array
    assert np.array_equal(vector_db.convert_to_numpy([1, 2, 3]), np.array([1, 2, 3]))

    # Test when an exception occurs during the conversion process
    with patch("numpy.array", side_effect=Exception("Failed to convert embeddings to numpy array")):
        with pytest.raises(Exception, match="Failed to convert embeddings to numpy array"):
            vector_db.convert_to_numpy([1, 2, 3])
