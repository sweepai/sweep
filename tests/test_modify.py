import unittest
from unittest.mock import MagicMock

from sweepai.agents.modify import modify
from sweepai.core.entities import FileChangeRequest
from sweepai.utils.github_utils import ClonedRepo

class TestModify(unittest.TestCase):
    def test_basic_modify(self):
        # Set up mocked inputs
        fcrs = [
            FileChangeRequest(
                filename="example.py",
                instructions="Change the greeting",
                change_type="modify"
            )
        ]
        request = "Update the greeting in example.py"
        cloned_repo = MagicMock(spec=ClonedRepo)
        cloned_repo.get_file_contents.return_value = 'print("Hello World")'
        relevant_filepaths = ["example.py"]
        
        # Call the modify function
        result = modify(fcrs, request, cloned_repo, relevant_filepaths)
        
        # Assert the expected result
        expected = {
            "example.py": {
                "original_contents": 'print("Hello World")',
                "contents": 'print("Hello SweepAI")'
            }
        }
        self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()