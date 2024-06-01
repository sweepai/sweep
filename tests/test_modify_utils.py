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
        self.assertEqual(indent("hello\nworld", 4), "    hello\n    world")

    def test_tokenize_code(self):
        code = "x = 1 # comment\n\nif x > 0:\n    print('positive')"
        expected_tokens = ["x", "=", "1", "if", "x", ">", "0", ":", "print", "(", "'positive'", ")"]
        self.assertEqual(tokenize_code(code), expected_tokens)

    def test_code_processor(self):
        code = "x = 1 # comment\n\nif x > 0:\n    print('positive')"
        expected_output = "x = 1 if x > 0 : print ( 'positive' )"
        self.assertEqual(code_processor(code), expected_output)

    def test_check_valid_parentheses(self):
        self.assertTrue(check_valid_parentheses("()"))
        self.assertTrue(check_valid_parentheses("()[]{}"))
        self.assertFalse(check_valid_parentheses("(]"))
        self.assertFalse(check_valid_parentheses("([)]"))

    def test_check_valid_parentheses_for_patch(self):
        self.assertEqual(check_valid_parentheses_for_patch("()", "()"), (0, 0, ""))
        self.assertEqual(check_valid_parentheses_for_patch("()", "())"), (0, 1, ")"))
        self.assertEqual(check_valid_parentheses_for_patch("(())", "()"), (1, 0, "("))
        self.assertEqual(check_valid_parentheses_for_patch("{[]}", "{[]}"), (0, 0, ""))

if __name__ == '__main__':
    unittest.main()