import unittest
from backend import function1, function2, function3

class TestBackend(unittest.TestCase):

    def test_function1(self):
        result = function1(input)
        self.assertEqual(result, expected_result)

    def test_function2(self):
        result = function2(input)
        self.assertEqual(result, expected_result)

    def test_function3(self):
        result = function3(input)
        self.assertEqual(result, expected_result)

if __name__ == '__main__':
    unittest.main()