import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from sweepai.core.vector_db import compute_embeddings, convert_to_numpy

@patch('sweepai.core.vector_db.embedding_function')
@patch('sweepai.core.vector_db.convert_to_numpy')
def test_compute_embeddings(mock_convert_to_numpy, mock_embedding_function):
    documents = ['doc1', 'doc2', 'doc3']
    embeddings = [np.array([1, 2, 3]), np.array([4, 5, 6]), np.array([7, 8, 9])]
    mock_embedding_function.return_value = embeddings
    mock_convert_to_numpy.return_value = np.array(embeddings)

    result = compute_embeddings(documents)

    mock_embedding_function.assert_called_once_with(documents)
    mock_convert_to_numpy.assert_called_once_with(embeddings, documents)
    assert np.array_equal(result[0], np.array(embeddings))

@patch('sweepai.core.vector_db.embedding_function')
@patch('sweepai.core.vector_db.convert_to_numpy')
def test_compute_embeddings_exception(mock_convert_to_numpy, mock_embedding_function):
    documents = ['doc1', 'doc2', 'doc3']
    embeddings = [np.array([1, 2, 3]), np.array([4, 5, 6]), np.array([7, 8, 9])]
    mock_embedding_function.return_value = embeddings
    mock_convert_to_numpy.side_effect = Exception('Failed to convert embeddings to numpy array')

    with pytest.raises(Exception) as e:
        compute_embeddings(documents)

    assert str(e.value) == 'Failed to convert embeddings to numpy array'

def test_convert_to_numpy():
    embeddings = [np.array([1, 2, 3]), np.array([4, 5, 6]), np.array([7, 8, 9])]
    documents = ['doc1', 'doc2', 'doc3']

    result = convert_to_numpy(embeddings, documents)

    assert np.array_equal(result, np.array(embeddings))

def test_convert_to_numpy_exception():
    embeddings = 'invalid embeddings'
    documents = ['doc1', 'doc2', 'doc3']

    with pytest.raises(Exception) as e:
        convert_to_numpy(embeddings, documents)

    assert str(e.value) == 'Failed to convert embeddings to numpy array, recomputing all of them'
