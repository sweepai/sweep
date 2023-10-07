import unittest

from sweepai.utils.docker_utils import get_latest_docker_version_date


class TestDockerUtils(unittest.TestCase):
    def test_get_latest_docker_version_date(self):
        date = get_latest_docker_version_date()
        self.assertIsNotNone(date)
        self.assertIsInstance(date, str)
