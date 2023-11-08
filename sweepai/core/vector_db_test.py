import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from sweepai.core import vector_db

def test_compute_embeddings():
    documents = ["doc1", "doc2", "doc3"]
    embeddings = [np.array([1, 2, 3]), np.array([4, 5, 6]), np.array([7, 8, 9])]

    with patch("sweepai.core.vector_db.embedding_function", return_value=embeddings) as mock_embedding_function, \
         patch("sweepai.core.vector_db.convert_to_numpy", side_effect=lambda x, y: np.array(x)) as mock_convert_to_numpy:

        result_embeddings, result_documents_to_compute, result_computed_embeddings, result_embedding = vector_db.compute_embeddings(documents)

        assert np.array_equal(result_embeddings, np.array(embeddings))
        assert result_documents_to_compute == []
        assert np.array_equal(result_computed_embeddings, np.array(embeddings))
        assert np.array_equal(result_embedding, np.array(embeddings[-1]))

        mock_embedding_function.assert_called_once_with(documents)
        mock_convert_to_numpy.assert_called_once_with(embeddings, documents)

def test_compute_embeddings_exception():
    documents = ["doc1", "doc2", "doc3"]
    embeddings = [np.array([1, 2, 3]), np.array([4, 5, 6]), "invalid"]

    with patch("sweepai.core.vector_db.embedding_function", return_value=embeddings) as mock_embedding_function, \
         patch("sweepai.core.vector_db.convert_to_numpy", side_effect=lambda x, y: np.array(x)) as mock_convert_to_numpy:

        with pytest.raises(Exception, match="Failed to convert embeddings to numpy array, recomputing all of them"):
            vector_db.compute_embeddings(documents)

def test_convert_to_numpy():
    embeddings = [np.array([1, 2, 3]), np.array([4, 5, 6]), np.array([7, 8, 9])]
    documents = ["doc1", "doc2", "doc3"]

    result = vector_db.convert_to_numpy(embeddings, documents)

    assert np.array_equal(result, np.array(embeddings))

def test_convert_to_numpy_exception():
    embeddings = [np.array([1, 2, 3]), np.array([4, 5, 6]), "invalid"]
    documents = ["doc1", "doc2", "doc3"]

    with pytest.raises(Exception, match="Failed to convert embeddings to numpy array, recomputing all of them"):
        vector_db.convert_to_numpy(embeddings, documents)
