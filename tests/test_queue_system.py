import unittest
from unittest.mock import patch
from sweepai.api import handle_pr_change_request, push_to_queue, PRChangeRequest

class TestQueueSystem(unittest.TestCase):
    @patch('sweepai.api.handle_comment')
    @patch('sweepai.api.handle_check_suite')
    def test_handle_pr_change_request(self, mock_handle_comment, mock_handle_check_suite):
        # Test the handle_pr_change_request function with a comment type PR change request
        pr_change_request = PRChangeRequest(type="comment", params={})
        handle_pr_change_request("repo", 1, pr_change_request)
        mock_handle_comment.assert_called_once()
    
        # Test the handle_pr_change_request function with a gha type PR change request
        pr_change_request = PRChangeRequest(type="gha", params={})
        handle_pr_change_request("repo", 1, pr_change_request)
        mock_handle_check_suite.assert_called_once()

    @patch('sweepai.api.handle_pr_change_request')
    def test_push_to_queue(self, mock_handle_pr_change_request):
        # Test the push_to_queue function
        pr_change_request = PRChangeRequest(type="comment", params={})
        push_to_queue("repo", 1, pr_change_request)
        mock_handle_pr_change_request.assert_called_once()

if __name__ == '__main__':
    unittest.main()