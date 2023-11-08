import numpy as np
import pytest
from unittest.mock import patch
from sweepai.core.vector_db import safe_numpy_conversion

def test_safe_numpy_conversion():
    # Create test data
    embeddings = np.random.rand(10, 300).tolist()
    documents = ["document" + str(i) for i in range(10)]

    # Test normal operation
    result = safe_numpy_conversion(embeddings, documents)
    assert isinstance(result, np.ndarray)

    # Test exception handling
    with patch("numpy.array", side_effect=Exception("Test exception")):
        result = safe_numpy_conversion(embeddings, documents)
        assert isinstance(result, np.ndarray)

    # Test normal operation again
    result = safe_numpy_conversion(embeddings, documents)
    assert isinstance(result, np.ndarray)
