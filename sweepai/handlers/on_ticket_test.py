import unittest
from unittest.mock import Mock, patch

from sweepai.handlers import on_ticket


class TestOnTicket(unittest.TestCase):
    @patch("sweepai.handlers.on_ticket.CURRENT_USERNAME", "bot")
    def test_delete_old_prs(self):
        # Mock repo and prs
        repo = Mock()
        prs = Mock()
        repo.get_pulls.return_value = prs

        # Mock PRs
        pr1 = Mock()
        pr1.user.login = "bot"
        pr1.body = "Fixes #123.\n"
        pr2 = Mock()
        pr2.user.login = "not_bot"
        pr2.body = "Fixes #123.\n"
        prs.get_page.return_value = [pr1, pr2]

        # Call function
        on_ticket.delete_old_prs()

        # Assert get_pulls was called correctly
        repo.get_pulls.assert_called_once_with(
            state="open",
            sort="created",
            direction="desc",
            base=on_ticket.SweepConfig.get_branch(repo),
        )

        # Assert get_page was called correctly
        prs.get_page.assert_called_once_with(0)

        # Assert safe_delete_sweep_branch was called correctly
        on_ticket.safe_delete_sweep_branch.assert_called_once_with(pr1, repo)
