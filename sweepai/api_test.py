import pytest

from sweepai.api import get_hash


def test_get_hash():
    hash_value = get_hash()
    assert len(hash_value) == 10, "The hash must be 10 characters"
    assert hash_value.isalnum(), "The hash should only contain alphanumeric characters"
