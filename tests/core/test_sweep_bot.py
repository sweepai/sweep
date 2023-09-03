import os
import unittest
from sweepai.core.sweep_bot import SweepBot

class TestSweepBot(unittest.TestCase):
    def test_check_file_size(self):
        # Create a file of a known size
        file_path = "test_file.txt"
        file_size = 60000
        with open(file_path, "wb") as f:
            f.write(os.urandom(file_size))

        # Initialize SweepBot
        bot = SweepBot()

        # Call check_file_size() and verify the result
        result = bot.check_file_size(file_path)
        self.assertTrue(result)

        # Clean up the created file
        os.remove(file_path)

if __name__ == "__main__":
    unittest.main()
