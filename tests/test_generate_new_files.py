import unittest
from sweep import generate_new_files

class TestGenerateNewFiles(unittest.TestCase):

    def test_generate_new_files(self):
        # Arrange
        expected_output = "Expected Output"

        # Act
        actual_output = generate_new_files("Input")

        # Assert
        self.assertEqual(actual_output, expected_output)

if __name__ == '__main__':
    unittest.main()

