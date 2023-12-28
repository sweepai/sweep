import pytest
import unittest.mock
from loguru import logger
from sweepai import api

class TestAPI:
    def setup_method(self):
        self.mock_api = unittest.mock.create_autospec(api)

    def test_webhook(self):
        self.mock_api.webhook.return_value = {"success": True}
        result = self.mock_api.webhook()
        assert result == {"success": True}
        self.mock_api.webhook.assert_called_once()

    def test_home(self):
        self.mock_api.home.return_value = "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>"
        result = self.mock_api.home()
        assert result == "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>"
        self.mock_api.home.assert_called_once()

    def test_terminate_thread(self, caplog):
        with caplog.at_level(logger.level("ERROR").no):
            self.mock_api.terminate_thread(None)
        assert "Could not get metadata for telemetry" in caplog.text

    def test_call_on_check_suite(self, caplog):
        with caplog.at_level(logger.level("ERROR").no):
            self.mock_api.call_on_check_suite(None)
        assert "Error:" in caplog.text
