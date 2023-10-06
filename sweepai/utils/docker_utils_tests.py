import unittest

from sweepai.utils.docker_utils import get_latest_docker_version


class TestDockerUtils(unittest.TestCase):
    def test_get_latest_docker_version(self):
        result = get_latest_docker_version()
        self.assertIsInstance(result, str)
        self.assertEqual(result, "actual_known_latest_version")


if __name__ == "__main__":
    unittest.main()
