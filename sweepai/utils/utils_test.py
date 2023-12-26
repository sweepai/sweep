import pytest

from sweepai.utils.utils import (check_code, check_syntax,
                                 check_valid_typescript, chunk_code,
                                 chunk_tree, get_line_number, naive_chunker,
                                 non_whitespace_len)


def test_non_whitespace_len():
    assert non_whitespace_len("hello world") == 10
    assert non_whitespace_len("   ") == 0
    assert non_whitespace_len("") == 0

def test_get_line_number():
    assert get_line_number(5, "hello\nworld") == 1
    assert get_line_number(0, "hello\nworld") == 0
    assert get_line_number(11, "hello\nworld") == 2

def test_chunk_tree():
    # Test with a simple tree and source code
    # This test will require a mock tree object

def test_naive_chunker():
    assert naive_chunker("hello\nworld", 1, 0) == ["hello", "world"]
    assert naive_chunker("hello\nworld", 2, 1) == ["hello\nworld"]
    assert naive_chunker("hello\nworld", 2, 0) == ["hello\nworld"]

def test_check_valid_typescript():
    assert check_valid_typescript("let x = 1;") == (True, "")
    assert check_valid_typescript("let x = ;") == (False, "Unexpected token ;")

def test_check_syntax():
    assert check_syntax("file.py", "x = 1") == (True, "")
    assert check_syntax("file.py", "x =") == (False, "Invalid syntax")

def test_check_code():
    assert check_code("file.py", "x = 1") == (True, "")
    assert check_code("file.py", "x =") == (False, "Invalid syntax")

def test_chunk_code():
    # Test with a simple code and path
    # This test will require a mock Snippet object
