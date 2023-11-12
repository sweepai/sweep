import pytest
from sweepai.handlers import pr_utils

def test_search_files_valid_input():
    # Arrange
    valid_input = # create valid input data
    expected_output = # create expected output data

    # Act
    result = pr_utils.search_files(valid_input)

    # Assert
    assert result == expected_output

def test_search_files_invalid_input():
    # Arrange
    invalid_input = # create invalid input data

    # Act and Assert
    with pytest.raises(Exception):
        pr_utils.search_files(invalid_input)

def test_create_pull_request_valid_input():
    # Arrange
    valid_input = # create valid input data
    expected_output = # create expected output data

    # Act
    result = pr_utils.create_pull_request(valid_input)

    # Assert
    assert result == expected_output

def test_create_pull_request_invalid_input():
    # Arrange
    invalid_input = # create invalid input data

    # Act and Assert
    with pytest.raises(Exception):
        pr_utils.create_pull_request(invalid_input)
