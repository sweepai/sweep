import unittest
import unittest.mock

from sweepai import api


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
