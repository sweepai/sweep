import unittest
import unittest.mock
from sweepai.utils.docker_utils import get_latest_docker_version

class TestDockerUtils(unittest.TestCase):
    def test_get_latest_docker_version_error(self):
        with unittest.mock.patch('requests.get', side_effect=requests.exceptions.RequestException):
            result = get_latest_docker_version()
            self.assertIsNone(result)


class TestDockerUtils(unittest.TestCase):
    def test_get_latest_docker_version(self):
        result = get_latest_docker_version()
        self.assertIsNotNone(result)
        self.assertTrue(isinstance(result, str))
        self.assertTrue(result != "")


if __name__ == "__main__":
    unittest.main()
