import unittest
import unittest.mock
from sweepai.core import sweep_bot

class TestSweepBot(unittest.TestCase):
    """
    Unit test class for testing the SweepBot class in sweep_bot.py
    """

    def test_get_first_10_lines_for_imports(self):
        """
        Test the function for getting the first 10 lines for imports in sweep_bot.py
        """
        # Mocking the dependencies
        sweep_bot_instance = sweep_bot.SweepBot()
        sweep_bot_instance.get_first_10_lines_for_imports = unittest.mock.Mock()

        # Test data
        test_data = "import os\nimport sys\n" * 10

        # Expected output
        expected_output = "import os\nimport sys\n" * 5

        # Call the function with test data
        actual_output = sweep_bot_instance.get_first_10_lines_for_imports(test_data)

        # Assert that the output is as expected
        self.assertEqual(actual_output, expected_output)

if __name__ == "__main__":
    unittest.main()
