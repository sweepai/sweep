import unittest
from sweepai import code_repair

class TestCodeRepair(unittest.TestCase):
    def setUp(self):
        self.repairer = code_repair.CodeRepair()

    def test_code_repair(self):
        broken_code = 'def foo():\n    return bar'
        fixed_code = 'def foo():\n    return "bar"'
        result = self.repairer.repair(broken_code)
        self.assertEqual(result, fixed_code)
</new_file>

