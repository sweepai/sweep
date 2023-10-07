import unittest
from unittest import mock
from sweepai.utils.docker_utils import get_latest_docker_version

class TestDockerUtils(unittest.TestCase):
    @mock.patch('requests.get')
    def test_get_latest_docker_version(self, mock_get):
        mock_get.return_value.json.return_value = {"results": [{"name": "1.0.0"}]}
        result = get_latest_docker_version()
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "")
