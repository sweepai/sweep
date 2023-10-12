import unittest
from unittest.mock import patch, Mock
from sweepai.health import check_sandbox_health, check_mongodb_health, check_redis_health

class TestHealth(unittest.TestCase):

    @patch('requests.get')
    @patch('sweepai.health.logger')
    def test_check_sandbox_health(self, mock_logger, mock_get):
        mock_response = Mock()
        mock_get.return_value = mock_response

        mock_response.raise_for_status.return_value = None
        self.assertEqual(check_sandbox_health(), "UP")

        mock_response.raise_for_status.side_effect = Exception()
        self.assertEqual(check_sandbox_health(), "DOWN")
        mock_logger.error.assert_called()

    @patch('pymongo.MongoClient')
    @patch('sweepai.health.logger')
    def test_check_mongodb_health(self, mock_logger, mock_client):
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance

        mock_client_instance.admin.command.return_value = None
        self.assertEqual(check_mongodb_health(), "UP")

        mock_client_instance.admin.command.side_effect = Exception()
        self.assertEqual(check_mongodb_health(), "DOWN")
        mock_logger.error.assert_called()

    @patch('redis.Redis.from_url')
    @patch('sweepai.health.logger')
    def test_check_redis_health(self, mock_logger, mock_redis):
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        mock_redis_instance.ping.return_value = None
        self.assertEqual(check_redis_health(), "UP")

        mock_redis_instance.ping.side_effect = Exception()
        self.assertEqual(check_redis_health(), "DOWN")
        mock_logger.error.assert_called()

if __name__ == "__main__":
    unittest.main()
