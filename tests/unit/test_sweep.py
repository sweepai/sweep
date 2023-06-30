import unittest
from sweep import Sweep

class TestSweep(unittest.TestCase):
    def setUp(self):
        self.sweep = Sweep()

    def test_method1(self):
        result = self.sweep.method1()
        self.assertEqual(result, expected_result)

    def test_method2(self):
        result = self.sweep.method2()
        self.assertEqual(result, expected_result)

if __name__ == '__main__':
    unittest.main()
