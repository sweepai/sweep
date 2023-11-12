import pytest
from sweepai.core.entities import FileChangeRequest
from sweepai.handlers.pr_utils import search_files, create_pull_request

def test_search_files():
    # Test with valid inputs
    file_change_requests = [FileChangeRequest(entity_display="file1"), FileChangeRequest(entity_display="file2")]
    result = search_files(file_change_requests)
    assert len(result) == 2
    assert all(isinstance(r, FileChangeRequest) for r in result)

    # Test with invalid inputs
    with pytest.raises(Exception):
        search_files([])

def test_create_pull_request():
    # Test with valid inputs
    pull_request = PullRequest(title="test", content="test content")
    result = create_pull_request(pull_request, "test_user", 123, 456)
    assert isinstance(result, PullRequest)
    assert result.title == "test"
    assert result.content == "test content"

    # Test with invalid inputs
    with pytest.raises(Exception):
        create_pull_request(None, "test_user", 123, 456)
