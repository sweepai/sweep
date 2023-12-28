import pytest

from sweepai.utils.progress import create_index


def test_create_index():
    result = create_index()
    assert result is None
