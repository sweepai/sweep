import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import sweepai.health as health_module

class TestHealthCheck(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(health_module.app)

    @patch('sweepai.health.check_sandbox_health', return_value="UP")
    @patch('sweepai.health.check_mongodb_health', return_value="UP")
    @patch('sweepai.health.check_redis_health', return_value="UP")
    @patch('psutil.cpu_percent', return_value=10.0)
    @patch('psutil.virtual_memory', return_value=unittest.mock.Mock(used=1000000))
    @patch('psutil.disk_usage', return_value=unittest.mock.Mock(used=1000000))
    @patch('psutil.net_io_counters', return_value=unittest.mock.Mock(bytes_sent=1000, bytes_recv=1000))
    def test_health_check(self, *_):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())
        self.assertIn("details", response.json())

if __name__ == "__main__":
    unittest.main()
