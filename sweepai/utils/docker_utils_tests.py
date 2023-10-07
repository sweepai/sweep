import unittest
from sweepai.utils.docker_utils import get_latest_docker_version

class TestDockerUtils(unittest.TestCase):
    def test_get_latest_docker_version(self):
        version = get_latest_docker_version()
        self.assertIsNotNone(version)

if __name__ == '__main__':
    unittest.main()
