from sweepai.core.code_repair import CodeRepairer
import unittest

class TestCodeRepair(unittest.TestCase):
    def test_repair_code(self):
        bad_code = '''
        def foo():
            print("Hello, world!")
            print("This is a bad line of code)
        '''
        expected_good_code = '''
        def foo():
            print("Hello, world!")
            print("This is a bad line of code")
        '''
        code_repairer = CodeRepairer()
        new_code = code_repairer.repair_code(bad_code)
        self.assertEqual(new_code, expected_good_code)

    # Add more test functions as needed

if __name__ == "__main__":
    unittest.main()

