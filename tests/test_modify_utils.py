import unittest
from sweepai.agents.modify_utils import english_join, indent, tokenize_code, code_processor, check_valid_parentheses, check_valid_parentheses_for_patch

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

if __name__ == "__main__":
    unittest.main()