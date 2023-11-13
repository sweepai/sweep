import pytest
from unittest.mock import MagicMock
from sweepai.handlers.pr_utils import search_files, create_pull_request

def test_search_files():
    # Mock data
    file_change_requests = [MagicMock(), MagicMock()]
    initial_sandbox_response = MagicMock()

    # Call function
    result = search_files(file_change_requests, initial_sandbox_response)

    # Expected result
    expected_result = [MagicMock(), MagicMock()]  # Replace with actual expected result

    # Assert that the result matches the expected result
    assert result == expected_result

def test_create_pull_request():
    # Mock data
    file_change_requests = [MagicMock(), MagicMock()]
    initial_sandbox_response = MagicMock()
    pull_request = MagicMock()

    # Call function
    result = create_pull_request(file_change_requests, initial_sandbox_response, pull_request)

    # Expected result
    expected_result = MagicMock()  # Replace with actual expected result

    # Assert that the result matches the expected result
    assert result == expected_result
