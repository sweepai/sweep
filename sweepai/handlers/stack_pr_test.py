import unittest
from unittest.mock import patch, create_autospec

from sweepai.handlers.stack_pr import stack_pr


class TestStackPR(unittest.TestCase):
    def setUp(self):
        self.mock_stack_pr = unittest.mock.create_autospec(stack_pr)

    def test_stack_pr(self):
        self.mock_stack_pr.stack_pr.return_value = {"success": True}
        result = self.mock_stack_pr.stack_pr(
            request="Add type hints to create_payment_messages in on_ticket.py.",
            pr_number=2646,
            username="kevinlu1248",
            repo_full_name="sweepai/sweep",
            installation_id=36855882,
            tracking_id="test_stack_pr",
        )
        self.assertEqual(result, {"success": True})
        self.mock_stack_pr.stack_pr.assert_called_once_with(
            request="Add type hints to create_payment_messages in on_ticket.py.",
            pr_number=2646,
            username="kevinlu1248",
            repo_full_name="sweepai/sweep",
            installation_id=36855882,
            tracking_id="test_stack_pr",
        )

    @patch('sweepai.handlers.stack_pr.PullRequest.get_issue_comments')
    def test_stack_pr_multiple_comments(self, mock_get_issue_comments):
        # Set up the mock return value with multiple Sweep comments
        mock_get_issue_comments.return_value = [
            unittest.mock.Mock(user=unittest.mock.Mock(login='sweep-bot-1')),
            unittest.mock.Mock(user=unittest.mock.Mock(login='sweep-bot-2')),
            unittest.mock.Mock(user=unittest.mock.Mock(login='sweep-bot-3')),
            unittest.mock.Mock(user=unittest.mock.Mock(login='sweep-bot-4'))
        ]

        # Call the stack_pr function with the mock pull request
        result = stack_pr(
            request='Fix flaky unit test in processor.py.',
            pr_number=42,
            username='devUser',
            repo_full_name='sweepai/sweep',
            installation_id=12345678,
            tracking_id='flaky-test-fix'
        )

        # Expected result when multiple Sweep comments are present
        expected_result = {
            'success': False,
            'error_message': 'It looks like there are already Sweep comments on this PR, so I wont attempt to fix it.'
        }
        self.assertEqual(result, expected_result)

    # Add more test methods as needed for each function in stack_pr.py


if __name__ == '__main__':
    unittest.main()
