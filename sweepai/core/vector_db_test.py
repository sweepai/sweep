import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from sweepai.core import vector_db

def test_compute_embeddings():
    # Mock the embedding_function and convert_to_numpy functions
    with patch.object(vector_db, "embedding_function", return_value=[1, 2, 3]), \
         patch.object(vector_db, "convert_to_numpy", return_value=np.array([1, 2, 3])):
        # Test when the embeddings can be successfully converted to a numpy array
        embeddings, _, _, _ = vector_db.compute_embeddings(["doc1", "doc2", "doc3"])
        assert np.array_equal(embeddings, np.array([1, 2, 3]))

        # Test when an exception occurs during the conversion process
        vector_db.convert_to_numpy.side_effect = Exception
        with pytest.raises(Exception):
            vector_db.compute_embeddings(["doc1", "doc2", "doc3"])

def test_convert_to_numpy():
    # Test when the embeddings can be successfully converted to a numpy array
    embeddings = vector_db.convert_to_numpy([1, 2, 3], ["doc1", "doc2", "doc3"])
    assert np.array_equal(embeddings, np.array([1, 2, 3]))

    # Test when an exception occurs during the conversion process
    with patch.object(vector_db, "embedding_function", side_effect=Exception):
        with pytest.raises(Exception):
            vector_db.convert_to_numpy([1, 2, 3], ["doc1", "doc2", "doc3"])
