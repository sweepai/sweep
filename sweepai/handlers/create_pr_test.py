import pytest
from unittest.mock import Mock, patch
from sweepai.handlers.create_pr import create_pr
from sweepai.core.entities import MaxTokensExceeded
import openai

@pytest.fixture
def mock_sweep_bot():
    mock_sweep_bot = Mock()
    mock_sweep_bot.repo.full_name = "test/repo"
    return mock_sweep_bot

def test_create_pr_no_changes(mock_sweep_bot):
    with patch.object(mock_sweep_bot, "change_files_in_github_iterator", return_value=[]), \
         patch.object(mock_sweep_bot.repo, "get_commits", return_value=Mock(totalCount=0)), \
         patch.object(mock_sweep_bot.repo, "get_git_ref", return_value=Mock()):
        result = create_pr([], Mock(), mock_sweep_bot, "test", 12345)
        assert not result["success"]
        mock_sweep_bot.repo.get_git_ref.assert_called_once_with("heads/test")

def test_create_pr_max_tokens_exceeded(mock_sweep_bot):
    with patch.object(mock_sweep_bot, "change_files_in_github_iterator", side_effect=MaxTokensExceeded()):
        with pytest.raises(MaxTokensExceeded):
            create_pr([], Mock(), mock_sweep_bot, "test", 12345)

def test_create_pr_invalid_request_error(mock_sweep_bot):
    with patch.object(mock_sweep_bot, "change_files_in_github_iterator", side_effect=openai.error.InvalidRequestError()):
        with pytest.raises(openai.error.InvalidRequestError):
            create_pr([], Mock(), mock_sweep_bot, "test", 12345)

def test_create_pr_unexpected_error(mock_sweep_bot):
    with patch.object(mock_sweep_bot, "change_files_in_github_iterator", side_effect=Exception()):
        with pytest.raises(Exception):
            create_pr([], Mock(), mock_sweep_bot, "test", 12345)

def test_create_pr_normal_case(mock_sweep_bot):
    with patch.object(mock_sweep_bot, "change_files_in_github_iterator", return_value=[(Mock(), 1, None, Mock(), [])]), \
         patch.object(mock_sweep_bot, "create_branch", return_value="test"), \
         patch.object(mock_sweep_bot.repo, "get_commits", return_value=Mock(totalCount=1)):
        result = create_pr([], Mock(), mock_sweep_bot, "test", 12345)
        assert result["success"]
