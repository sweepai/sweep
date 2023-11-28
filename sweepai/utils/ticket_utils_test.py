from unittest.mock import Mock, patch

import pytest

from sweepai.utils.ticket_utils import review_code


@pytest.fixture
def review_code_params():
    return {
        'repo': Mock(),
        'pr_changes': Mock(),
        'issue_url': 'https://github.com/sweepai/sweep/issues/1',
        'username': 'test_user',
        'repo_description': 'Test repo',
        'title': 'Test title',
        'summary': 'Test summary',
        'replies_text': 'Test replies text',
        'tree': Mock(),
        'lint_output': 'Test lint output',
        'plan': 'Test plan',
        'chat_logger': Mock(),
        'review_message': 'Test review message',
        'edit_sweep_comment': Mock(),
        'repo_full_name': 'sweepai/sweep',
        'installation_id': '1234567890',
    }

def test_review_code_success(review_code_params):
    changes_required, review_message = review_code(**review_code_params)
    assert changes_required is False
    assert 'Test review message' in review_message

def test_review_code_edge_case(review_code_params):
    review_code_params['title'] = ''  # Edge case: empty title
    with pytest.raises(ValueError):
        review_code(**review_code_params)

def test_review_code_fail_path(review_code_params):
    review_code_params['repo'] = None  # Fail path: None repo
    with pytest.raises(TypeError):
        review_code(**review_code_params)

@patch('sweepai.utils.ticket_utils.on_comment')
def test_review_code_mock_on_comment(mock_on_comment, review_code_params):
    review_code(**review_code_params)
    mock_on_comment.assert_called_once()
