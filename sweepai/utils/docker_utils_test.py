import unittest

from sweepai.utils.docker_utils import get_latest_docker_version


class TestDockerUtils(unittest.TestCase):
    def test_get_latest_docker_version(self):
        result = get_latest_docker_version()
        self.assertIsInstance(result, str)
        self.assertTrue(
            result == "just now"
            or " minutes ago" in result
            or " hours ago" in result
            or " days ago" in result
        )
