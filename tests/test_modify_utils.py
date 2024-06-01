import unittest
from unittest.mock import MagicMock
from sweepai.agents.modify_utils import english_join, indent, tokenize_code, code_processor, check_valid_parentheses, check_valid_parentheses_for_patch, handle_submit_task

class TestModifyUtils(unittest.TestCase):
    def test_english_join(self):
        self.assertEqual(english_join([]), "")
        self.assertEqual(english_join(["apple"]), "apple")
        self.assertEqual(english_join(["apple", "banana"]), "apple and banana")
        self.assertEqual(english_join(["apple", "banana", "cherry"]), "apple, banana, and cherry")

    def test_indent(self):
        self.assertEqual(indent("", 2), "")
        self.assertEqual(indent("hello", 2), "  hello")
        self.assertEqual(indent("hello\nworld", 2), "  hello\n  world")
        self.assertEqual(indent("hello\nworld\n", 4), "    hello\n    world\n")

    def test_tokenize_code(self):
        self.assertEqual(tokenize_code(""), [])
        self.assertEqual(tokenize_code("# comment"), [])
        self.assertEqual(tokenize_code("   "), [])
        self.assertEqual(tokenize_code("def foo():\n    pass"), ["def", "foo", "(", ")", ":", "pass"])

    def test_code_processor(self):
        self.assertEqual(code_processor(""), "")
        self.assertEqual(code_processor("# comment"), "")
        self.assertEqual(code_processor("   "), "")
        self.assertEqual(code_processor("def foo():\n    pass"), "def foo ( ) : pass")

    def test_check_valid_parentheses(self):
        self.assertTrue(check_valid_parentheses(""))
        self.assertTrue(check_valid_parentheses("()"))
        self.assertTrue(check_valid_parentheses("()[]{}"))
        self.assertFalse(check_valid_parentheses("(]"))
        self.assertFalse(check_valid_parentheses("([)]"))

    def test_check_valid_parentheses_for_patch(self):
        self.assertEqual(check_valid_parentheses_for_patch("", ""), (0, 0, ""))
        self.assertEqual(check_valid_parentheses_for_patch("()", "()"), (0, 0, ""))
        self.assertEqual(check_valid_parentheses_for_patch("()", "())"), (0, 1, ")"))
        self.assertEqual(check_valid_parentheses_for_patch("(())", "()"), (1, 0, "("))
        self.assertEqual(check_valid_parentheses_for_patch("{[]}", "{[]}"), (0, 0, ""))
        self.assertEqual(check_valid_parentheses_for_patch("{[]}", "{[]}}"), (0, 1, "}"))

    def test_handle_submit_task(self):
        # Test case where changes were made
        modify_files_dict = {
            "file1.py": {"contents": "new content", "original_contents": "old content"}
        }
        llm_state = {
            "fcrs": [MagicMock(is_completed=False), MagicMock(is_completed=False)],
            "completed_changes_per_fcr": [0, 0],
            "done_counter": 0,
            "attempt_count": 0,
            "current_task": "original task",
        }
    
        llm_response, updated_llm_state = handle_submit_task(modify_files_dict, llm_state)
    
        assert llm_response == "SUCCESS\n\nThe previous task is now complete. Please move on to the next task. original task"
        assert updated_llm_state["fcrs"][0].is_completed == True
        assert updated_llm_state["attempt_count"] == 0
        assert updated_llm_state["attempt_lazy_change"] == True
        assert updated_llm_state["visited_set"] == set()
    
        # Test case where no changes were made
        modify_files_dict = {
            "file1.py": {"contents": "same content", "original_contents": "same content"}
        }
        llm_state = {
            "fcrs": [MagicMock(is_completed=False), MagicMock(is_completed=False)],
            "completed_changes_per_fcr": [0, 0],
            "done_counter": 0,
            "attempt_count": 0,
            "current_task": "original task",
        }
    
        llm_response, updated_llm_state = handle_submit_task(modify_files_dict, llm_state)
    
        assert llm_response == "ERROR\n\nNo changes were made. Please continue working on your task."
        assert updated_llm_state["done_counter"] == 1
    
        # Test case where all tasks are completed
        modify_files_dict = {
            "file1.py": {"contents": "new content", "original_contents": "old content"}
        }
        llm_state = {
            "fcrs": [MagicMock(is_completed=True), MagicMock(is_completed=True)],
            "completed_changes_per_fcr": [0, 0],
            "done_counter": 0,
            "attempt_count": 0,
            "current_task": "original task",
        }
    
        llm_response, updated_llm_state = handle_submit_task(modify_files_dict, llm_state)
    
        assert llm_response == "DONE"
    
    def test_handle_submit_task():
        # Test case where changes were made
        modify_files_dict = {
            "file1.py": {"contents": "new content", "original_contents": "old content"}
        }
        llm_state = {
            "fcrs": [MagicMock(is_completed=False), MagicMock(is_completed=False)],
            "completed_changes_per_fcr": [0, 0],
            "done_counter": 0,
            "attempt_count": 0,
            "current_task": "original task",
        }
    
        llm_response, updated_llm_state = handle_submit_task(modify_files_dict, llm_state)
    
        assert llm_response == "SUCCESS\n\nThe previous task is now complete. Please move on to the next task. original task"
        assert updated_llm_state["fcrs"][0].is_completed == True
        assert updated_llm_state["attempt_count"] == 0
        assert updated_llm_state["attempt_lazy_change"] == True
        assert updated_llm_state["visited_set"] == set()
    
        # Test case where no changes were made
        modify_files_dict = {
            "file1.py": {"contents": "same content", "original_contents": "same content"}
        }
        llm_state = {
            "fcrs": [MagicMock(is_completed=False), MagicMock(is_completed=False)],
            "completed_changes_per_fcr": [0, 0],
            "done_counter": 0,
            "attempt_count": 0,
            "current_task": "original task",
        }
    
        llm_response, updated_llm_state = handle_submit_task(modify_files_dict, llm_state)
    
        assert llm_response == "ERROR\n\nNo changes were made. Please continue working on your task."
        assert updated_llm_state["done_counter"] == 1
    
        # Test case where all tasks are completed
        modify_files_dict = {
            "file1.py": {"contents": "new content", "original_contents": "old content"}
        }
        llm_state = {
            "fcrs": [MagicMock(is_completed=True), MagicMock(is_completed=True)],
            "completed_changes_per_fcr": [0, 0],
            "done_counter": 0,
            "attempt_count": 0,
            "current_task": "original task",
        }
    
        llm_response, updated_llm_state = handle_submit_task(modify_files_dict, llm_state)
    
        assert llm_response == "DONE"

if __name__ == "__main__":
    unittest.main()