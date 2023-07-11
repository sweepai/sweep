import unittest
from sweepai.app.backend import function1, function2, function3

class TestBackend(unittest.TestCase):
    def test_function1(self):
        print("Hello World")
        # TODO: Replace with actual test
        result = function1(input)
        self.assertEqual(result, expected_output)

    def test_function2(self):
        # TODO: Replace with actual test
        result = function2(input)
        self.assertEqual(result, expected_output)

    def test_function3(self):
        # TODO: Replace with actual test
        result = function3(input)
        self.assertEqual(result, expected_output)

if __name__ == '__main__':
    unittest.main()