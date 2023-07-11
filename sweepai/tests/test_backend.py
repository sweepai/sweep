import unittest
from backend import function1, function2, function3

class TestBackend(unittest.TestCase):

    def test_function1(self):
        self.assertEqual(function1('input'), 'expected_output')

    def test_function2(self):
        self.assertEqual(function2('input'), 'expected_output')

    def test_function3(self):
        self.assertEqual(function3('input'), 'expected_output')

if __name__ == '__main__':
    unittest.main()