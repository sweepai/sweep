import unittest
from unittest.mock import MagicMock

from sweepai.agents.modify import handle_function_call
from sweepai.core.entities import AnthropicFunctionCall
from sweepai.utils.github_utils import ClonedRepo

class TestModify(unittest.TestCase):

    def test_handle_function_call(self):
        # Set up mock input arguments
        cloned_repo = MagicMock(spec=ClonedRepo)
        function_call = AnthropicFunctionCall(
            function_name="make_change",
            function_parameters={
                "justification": "Test justification",
                "file_name": "test_file.py",  
                "original_code": "original code block",
                "new_code": "new code block"
            }
        )
        modify_files_dict = {}
        llm_state = {"initial_check_results": {}}
        
        # Call function under test
        response, updated_files, updated_state = handle_function_call(
            cloned_repo, 
            function_call,
            modify_files_dict,
            llm_state
        )
        
        # Assert expected output
        self.assertEqual(response, "SUCCESS\n\nThe following changes have been applied:\n\n```diff\n@@ -1,1 +1,1 @@\n-original code block\n+new code block\n```\nBefore proceeding, it is important to review and critique the changes you have made. Follow these steps:\n\na. Review CURRENT TASK for requirements.\nb. Analyze code patch:\n    - Incorrect indentations that does not match surrounding code\n    - Unnecessary deletions\n    - Logic errors\n    - Unhandled edge cases\n    - Missing imports\n    - Incomplete changes\n    - Usage of nullable attributes\n    - Non-functional code\n    - Misalignment with plan and requirements\nc. Perform critical contextual analysis:\n    - Break down changes \n    - Explain reasoning\n    - Identify logic issues, edge cases, plan deviations\n    - Consider all scenarios and pitfalls\n    - Consider backwards compatibility and future-proofing\n    - Suggest fixes for problems\n    - Evaluate error handling and fallback mechanisms\nd. Be extremely critical. Do not overlook ANY issues.\ne. Finally decide whether additional changes are needed or if the task is complete.\n\nIf additional changes are needed, make the necessary changes and call the make_change function again. If the task is complete, call the submit_task function.")
        self.assertIn("test_file.py", updated_files)
        self.assertEqual(updated_files["test_file.py"]["contents"], "new code block")
        self.assertTrue(updated_state["attempt_lazy_change"])