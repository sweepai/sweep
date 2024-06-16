import unittest
import unittest.mock

from sweepai.handlers import on_ticket, stack_pr


class TestStackPR(unittest.TestCase):
    def setUp(self):
        self.mock_on_ticket = unittest.mock.create_autospec(on_ticket)

    def test_on_ticket(self):
        mock_title = "test_title"
        mock_summary = "test_summary"
        mock_issue_number = 123
        mock_issue_url = "https://github.com/sweepai/sweep/issues/123"
        mock_username = "test_user"
        mock_repo_full_name = "sweepai/sweep"
        mock_repo_description = "test_repo_description"
        mock_installation_id = 123456
        mock_comment_id = 789
        mock_edited = False

        self.mock_on_ticket.on_ticket.return_value = {"success": True}
        result = on_ticket(
            mock_title,
            mock_summary,
            mock_issue_number,
            mock_issue_url,
            mock_username,
            mock_repo_full_name,
            mock_repo_description,
            mock_installation_id,
            mock_comment_id,
            mock_edited,
        )
        self.assertEqual(result, {"success": True})
        self.mock_on_ticket.on_ticket.assert_called_once_with(
            mock_title,
            mock_summary,
            mock_issue_number,
            mock_issue_url,
            mock_username,
            mock_repo_full_name,
            mock_repo_description,
            mock_installation_id,
            mock_comment_id,
            mock_edited,
        )

if __name__ == '__main__':
    unittest.main()
