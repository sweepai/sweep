import unittest
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

    # Add more test methods as needed for each function in stack_pr.py


if __name__ == '__main__':
    unittest.main()
