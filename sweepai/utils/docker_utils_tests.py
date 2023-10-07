import unittest

from sweepai.utils.docker_utils import get_latest_docker_version_date


class TestDockerUtils(unittest.TestCase):
    def test_get_latest_docker_version_date(self):
        result = get_latest_docker_version_date()
        self.assertIsInstance(result, str)
        self.assertRegex(result, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")
