import unittest
from unittest import mock
from sweepai.utils.docker_utils import get_latest_docker_version

class TestDockerUtils(unittest.TestCase):
    @mock.patch('sweepai.utils.docker_utils.requests.get')
    @mock.patch('sweepai.utils.docker_utils.logging.getLogger')
    def test_get_latest_docker_version(self, mock_get, mock_logger):
        # Test case where requests.get raises an exception
        mock_get.side_effect = Exception
        result = get_latest_docker_version()
        self.assertIsNone(result)

        # Test case where requests.get returns a response without the expected data
        mock_get.side_effect = None
        mock_get.return_value.json.return_value = {}
        result = get_latest_docker_version()
        self.assertIsNone(result)

        # Test case where requests.get returns a valid response
        mock_get.return_value.json.return_value = {'results': [{'last_updated': '2021-01-01T00:00:00Z'}]}
        result = get_latest_docker_version()
        self.assertEqual(result, '2021-01-01T00:00:00Z')

if __name__ == '__main__':
    unittest.main()
