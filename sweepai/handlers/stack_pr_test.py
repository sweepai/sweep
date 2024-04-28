import unittest
import unittest.mock
import unittest.mock

from sweepai.handlers import stack_pr


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

    def test_stack_pr_open(self):
        mock_pr = unittest.mock.create_autospec(stack_pr.stack_pr, return_value={"success": True, "state": "open"})
        mock_pr.return_value.state = "open"
        result = mock_pr()
        self.assertEqual(result, {"success": True})

    def test_stack_pr_not_open(self):
        mock_pr = unittest.mock.create_autospec(stack_pr.stack_pr, return_value={"success": False, "error_message": "This PR is not open, so I won't attempt to fix it.", "state": "closed"})
        mock_pr.return_value.state = "closed"
        result = mock_pr()
        self.assertEqual(result, {"success": False, "error_message": "This PR is not open, so I won't attempt to fix it."})

    # Add more test methods as needed for each function in stack_pr.py


if __name__ == '__main__':
    unittest.main()
