import unittest
from unittest.mock import patch

from sweepai.agents.name_agent import NameBot, serialize_method_name


class TestSerializeMethodName(unittest.TestCase):
    def test_regular_name(self):
        self.assertEqual(serialize_method_name("function_name"), "function_name")

    def test_strip_quotes(self):
        self.assertEqual(serialize_method_name('"function_name"'), "function_name")

    def test_handle_numbered_name(self):
        self.assertEqual(serialize_method_name('1. "function_name"'), "function_name")

    def test_name_with_period_but_not_numbered(self):
        self.assertEqual(serialize_method_name("func.tion.name"), "func.tion.name")

    def test_name_with_leading_trailing_spaces(self):
        self.assertEqual(serialize_method_name("  function_name  "), "function_name")


# Corrected test case for NameBot with mock response
class TestNameBotNameFunctions(unittest.TestCase):
    def setUp(self):
        self.name_bot = NameBot()  # Instance of NameBot

    @patch.object(
        NameBot,
        "chat",
        return_value="<function_name>\nnaming_function\n</function_name>",
    )
    def test_name_functions_single_result(self, mock_chat):
        result = self.name_bot.name_functions(
            old_code="def old_func(): pass",
            snippets="Snippet 1 content",
            existing_names="existing_func",
            count=1,
        )
        self.assertEqual(result, ["naming_function"])

    @patch.object(
        NameBot,
        "chat",
        return_value="""<function_name>
naming_function_one
</function_name>
<function_name>
naming_function_two
</function_name>""",
    )
    def test_name_functions_multiple_results(self, mock_chat):
        result = self.name_bot.name_functions(
            old_code="def old_func(): pass",
            snippets="Snippet 1 content\nSnippet 2 content",
            existing_names="existing_func_one\nexisting_func_two",
            count=2,
        )
        self.assertEqual(result, ["naming_function_one", "naming_function_two"])


if __name__ == "__main__":
    unittest.main()
