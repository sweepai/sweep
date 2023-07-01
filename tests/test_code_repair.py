import unittest
from sweepai import code_repair

class TestCodeRepair(unittest.TestCase):
    def setUp(self):
        self.code_repair = code_repair.CodeRepair()

    def test_repair(self):
        code = "def add(x, y): return x + y"
        result = self.code_repair.repair(code)
        self.assertIsNotNone(result)

        code = ""
        result = self.code_repair.repair(code)
        self.assertIsNone(result)

    def test_repair_exception(self):
        with self.assertRaises(Exception):
            self.code_repair.repair(None)
</new_file>

