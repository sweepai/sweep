import unittest
from unittest.mock import MagicMock, patch
from sweepai.agents.modify_utils import (
    english_join,
    indent,
    tokenize_code,
    code_processor,
    check_valid_parentheses,
    check_valid_parentheses_for_patch,
    find_best_matches,
    find_best_match,
    find_max_indentation,
    find_smallest_valid_superspan,
    contains_ignoring_whitespace,
    validate_and_parse_function_call,
    create_user_message,
    changes_made,
    render_plan,
    render_current_task,
    tasks_completed,
    get_replaces_per_fcr,
    compile_fcr,
    generate_diffs,
    generate_diff_string,
    create_tool_call_response,
    get_latest_contents,
    get_surrounding_lines,
    check_make_change_tool_call,
    validate_indents,
    handle_submit_task,
    finish_applying_changes,
    handle_create_file,
    handle_function_call,
)
from sweepai.core.entities import FileChangeRequest, AnthropicFunctionCall
from sweepai.utils.github_utils import ClonedRepo

class TestModifyUtils(unittest.TestCase):
    
    def test_english_join(self):
        self.assertEqual(english_join([]), "")
        self.assertEqual(english_join(["apple"]), "apple")
        self.assertEqual(english_join(["apple", "banana"]), "apple and banana")
        self.assertEqual(english_join(["apple", "banana", "cherry"]), "apple, banana, and cherry")

    def test_indent(self):
        self.assertEqual(indent("hello\nworld", 2), "  hello\n  world")
        self.assertEqual(indent("hello\n\nworld", 4), "    hello\n\n    world")

    def test_tokenize_code(self):
        code = "def foo():\n  print('hello')\n# comment\n  return 42"
        expected = ["def", "foo", "(", ")", ":", "print", "(", "'hello'", ")", "return", "42"]
        self.assertEqual(tokenize_code(code), expected)

    def test_code_processor(self):
        code = "def foo():\n  print('hello')\n# comment\n  return 42"
        expected = "def foo ( ) : print ( 'hello' ) return 42"
        self.assertEqual(code_processor(code), expected)

    def test_check_valid_parentheses(self):
        self.assertTrue(check_valid_parentheses("()"))
        self.assertTrue(check_valid_parentheses("([]{})"))
        self.assertFalse(check_valid_parentheses("(]"))
        self.assertFalse(check_valid_parentheses("([)]"))

    def test_check_valid_parentheses_for_patch(self):
        self.assertEqual(check_valid_parentheses_for_patch("()", "()"), (0, 0, ""))
        self.assertEqual(check_valid_parentheses_for_patch("()", "(())"), (1, 0, ")"))
        self.assertEqual(check_valid_parentheses_for_patch("{[()]}", "{[]}"), (0, 2, "("))

    def test_find_best_matches(self):
        haystack = "The quick brown fox jumps over the lazy dog"
        self.assertEqual(find_best_matches("fox", haystack), [("fox", 100)])
        self.assertEqual(find_best_matches("cat", haystack), [])
        self.assertEqual(find_best_matches("o", haystack), [("over", 90), ("fox", 90), ("dog", 90), ("brown", 86)])

    def test_find_best_match(self):
        haystack = "The quick brown fox jumps over the lazy dog"
        self.assertEqual(find_best_match("fox", haystack), ("fox", 100))
        self.assertEqual(find_best_match("cat", haystack), ("", 0))

    def test_find_max_indentation(self):
        code = "def foo():\n    if True:\n        print('hello')\n"
        self.assertEqual(find_max_indentation(code), 8)

    def test_find_smallest_valid_superspan(self):
        haystack = "if (foo):\n    print('hello')\nelse:\n    print('world')"
        self.assertEqual(find_smallest_valid_superspan("print('hello')", haystack), "    print('hello')")
        self.assertEqual(find_smallest_valid_superspan("foo", haystack), "if (foo):\n    print('hello')")

    def test_contains_ignoring_whitespace(self):
        haystack = "if (foo):\n    print('hello')\nelse:\n    print('world')"
        self.assertEqual(contains_ignoring_whitespace("print('hello')", haystack), (1, 2))
        self.assertFalse(contains_ignoring_whitespace("print('goodbye')", haystack))

    @patch("sweepai.agents.modify_utils.parse_function_calls")
    def test_validate_and_parse_function_call(self, mock_parse_function_calls):
        mock_chat_gpt = MagicMock()
        mock_parse_function_calls.return_value = [{"tool": "foo", "arguments": {"bar": "baz"}}]
        
        result = validate_and_parse_function_call("<function_call>foo</function_call>", mock_chat_gpt)
        self.assertEqual(result.function_name, "foo")
        self.assertEqual(result.function_parameters, {"bar": "baz"})
        
        mock_parse_function_calls.return_value = []
        result = validate_and_parse_function_call("invalid", mock_chat_gpt)
        self.assertIsNone(result)

    @patch("sweepai.agents.modify_utils.get_latest_contents")
    def test_create_user_message(self, mock_get_latest_contents):
        mock_fcrs = [
            FileChangeRequest(filename="file1.py", change_type="modify", instructions="Change foo to bar"),
            FileChangeRequest(filename="file2.py", change_type="create", instructions="Add a new function baz"),
        ]
        mock_cloned_repo = MagicMock(spec=ClonedRepo)
        mock_cloned_repo.get_file_list.return_value = ["file1.py", "file2.py"]
        mock_cloned_repo.get_file_contents.side_effect = ["original content 1", "original content 2"]
        mock_get_latest_contents.side_effect = ["modified content 1", "modified content 2"]
        
        result = create_user_message(mock_fcrs, "Test request", mock_cloned_repo, modify_files_dict={"file1.py": {"contents": "modified content 1"}})
        self.assertIn("Test request", result)
        self.assertIn("Change foo to bar", result)
        self.assertIn("Add a new function baz", result)
        self.assertIn("modified content 1", result)
        self.assertIn("original content 2", result)

    def test_changes_made(self):
        modify_files_dict = {
            "file1.py": {"contents": "new content", "original_contents": "old content"},
            "file2.py": {"contents": "same content", "original_contents": "same content"},
        }
        self.assertTrue(changes_made(modify_files_dict, {}))
        self.assertFalse(changes_made(modify_files_dict, modify_files_dict))

    def test_render_plan(self):
        mock_fcrs = [
            FileChangeRequest(filename="file1.py", change_type="modify", instructions="Change foo to bar", is_completed=True),
            FileChangeRequest(filename="file2.py", change_type="create", instructions="Add a new function baz", is_completed=False),
        ]
        result = render_plan(mock_fcrs)
        self.assertIn("You have 2 changes to make", result)
        self.assertIn("You have previously modified file1.py", result)
        self.assertIn("Your CURRENT TASK is to create file2.py", result)

    def test_render_current_task(self):
        mock_fcrs = [
            FileChangeRequest(filename="file1.py", change_type="modify", instructions="Change foo to bar", is_completed=True),
            FileChangeRequest(filename="file2.py", change_type="create", instructions="Add a new function baz", is_completed=False),
        ]
        result = render_current_task(mock_fcrs)
        self.assertIn("The CURRENT TASK is to create file2.py", result)
        self.assertIn("Add a new function baz", result)

    def test_tasks_completed(self):
        mock_fcrs = [
            FileChangeRequest(filename="file1.py", change_type="modify", instructions="Change foo to bar", is_completed=True),
            FileChangeRequest(filename="file2.py", change_type="create", instructions="Add a new function baz", is_completed=False),
        ]
        self.assertEqual(tasks_completed(mock_fcrs), 1)

    def test_get_replaces_per_fcr(self):
        fcr = FileChangeRequest(filename="file1.py", change_type="modify", instructions="<original_code>foo</original_code><new_code>bar