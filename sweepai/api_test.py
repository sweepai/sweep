import unittest
import unittest.mock
from sweepai.api import worker

class TestWorker(unittest.TestCase):
    def setUp(self):
        self.mock_request = unittest.mock.Mock()

    def test_worker_with_valid_input(self):
        # Set up mock request with valid data
        self.mock_request.json.return_value = {"valid": "data"}

        # Call the worker function with the mock request
        result = worker(self.mock_request)

        # Assert that the function returns the expected result
        self.assertEqual(result, {"success": True})

    def test_worker_with_invalid_input(self):
        # Set up mock request with invalid data
        self.mock_request.json.return_value = {"invalid": "data"}

        # Assert that the worker function raises an HTTPException for invalid input
        with self.assertRaises(HTTPException):
            worker(self.mock_request)

if __name__ == "__main__":
    unittest.main()
