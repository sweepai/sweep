import threading
import time
import unittest
import unittest.mock

from sweepai import api
from sweepai.api import terminate_thread, delayed_kill, call_on_ticket


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.mock_api = unittest.mock.create_autospec(api)

    def test_webhook(self):
        self.mock_api.webhook.return_value = {"success": True}
        result = self.mock_api.webhook()
        self.assertEqual(result, {"success": True})
        self.mock_api.webhook.assert_called_once()

    def test_home(self):
        self.mock_api.home.return_value = "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>"
        result = self.mock_api.home()
        self.assertEqual(result, "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>")
        self.mock_api.home.assert_called_once()

    # Add more test methods as needed for each function in api.py

if __name__ == '__main__':
    unittest.main()
    def test_terminate_thread(self):
        mock_thread = unittest.mock.Mock()
        mock_thread.is_alive.return_value = True
        api.terminate_thread(mock_thread)
        self.assertFalse(mock_thread.is_alive())

    def test_delayed_kill(self):
        mock_thread = unittest.mock.Mock()
        mock_thread.is_alive.return_value = True
        api.delayed_kill(mock_thread, delay=0.1)
        time.sleep(0.2)
        self.assertFalse(mock_thread.is_alive())

    def test_call_on_ticket_new_thread(self):
        mock_repo_full_name = "mock/repo"
        mock_issue_number = 1
        api.on_ticket_events = {}
        api.call_on_ticket(repo_full_name=mock_repo_full_name, issue_number=mock_issue_number)
        self.assertIn(f"{mock_repo_full_name}-{mock_issue_number}", api.on_ticket_events)
        self.assertTrue(api.on_ticket_events[f"{mock_repo_full_name}-{mock_issue_number}"].is_alive())

    def test_call_on_ticket_existing_thread(self):
        mock_repo_full_name = "mock/repo"
        mock_issue_number = 1
        mock_thread = unittest.mock.Mock()
        mock_thread.is_alive.return_value = True
        api.on_ticket_events = {f"{mock_repo_full_name}-{mock_issue_number}": mock_thread}
        api.call_on_ticket(repo_full_name=mock_repo_full_name, issue_number=mock_issue_number)
        self.assertFalse(mock_thread.is_alive())
        self.assertTrue(api.on_ticket_events[f"{mock_repo_full_name}-{mock_issue_number}"].is_alive())
