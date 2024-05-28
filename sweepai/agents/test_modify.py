import unittest
from sweepai.agents.modify import modify

class TestModify(unittest.TestCase):
    def test_modify_single_file(self):
        # Set up test data
        fcrs = [
            FileChangeRequest(
                filename="example.py",
                change_type="modify",
                instructions="Replace 'Hello, World!' with 'Hello, Sweep!'"
            )
        ]
        request = "Update the greeting in example.py"
        cloned_repo = ClonedRepo("test_repo")
        relevant_filepaths = ["example.py"]
        
        # Call the modify function
        result = modify(fcrs, request, cloned_repo, relevant_filepaths)
        
        # Assert the expected changes were made
        self.assertIn("example.py", result)
        self.assertIn("Hello, Sweep!", result["example.py"]["contents"])
        self.assertNotIn("Hello, World!", result["example.py"]["contents"])