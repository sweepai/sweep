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
    @mock.patch('requests.get')
    def test_get_latest_docker_version_unsorted_versions(self, mock_get):
        mock_get.return_value.json.return_value = {"results": [{"name": "1.0.0"}, {"name": "2.0.0"}, {"name": "0.5.0"}]}
        result = get_latest_docker_version()
        self.assertEqual(result, "2.0.0")

    @mock.patch('requests.get')
    def test_get_latest_docker_version_empty_response(self, mock_get):
        mock_get.return_value.json.return_value = {"results": []}
        with self.assertRaises(Exception):
            get_latest_docker_version()

    @mock.patch('requests.get')
    def test_get_latest_docker_version_invalid_response(self, mock_get):
        mock_get.return_value.json.return_value = {"unexpected": "response"}
        with self.assertRaises(Exception):
            get_latest_docker_version()
