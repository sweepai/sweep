import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sweepai.web.health import (
    app,
    check_mongodb_health,
    check_redis_health,
    check_sandbox_health,
)


@unittest.skip("Fails")
class TestHealth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("sweepai.health.requests.get")
    def test_check_sandbox_health(self, mock_get):
        mock_get.return_value.status_code = 200
        response = check_sandbox_health()
        self.assertEqual(response, "UP")

        mock_get.return_value.status_code = 500
        response = check_sandbox_health()
        self.assertEqual(response, "DOWN")

    @patch("sweepai.health.MongoClient")
    def test_check_mongodb_health(self, mock_client):
        mock_client.admin.command.return_value = True
        response = check_mongodb_health()
        self.assertEqual(response, "UP")

        mock_client.admin.command.side_effect = Exception()
        response = check_mongodb_health()
        self.assertEqual(response, "DOWN")

    @patch("sweepai.health.redis.Redis")
    def test_check_redis_health(self, mock_redis):
        mock_redis.ping.return_value = True
        response = check_redis_health()
        self.assertEqual(response, "UP")

        mock_redis.ping.side_effect = Exception()
        response = check_redis_health()
        self.assertEqual(response, "DOWN")

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())
        self.assertIn("details", response.json())
