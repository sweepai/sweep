import unittest
from unittest.mock import patch

from sweepai.agents.graph_child import GraphChildBot, extract_python_span


class TestGraphChild(unittest.TestCase):
    def setUp(self):
        self.bot = GraphChildBot()

    def test_code_plan_extraction_no_entities(self):
        code = "print('Hello, world!')"
        entities = None

        result = extract_python_span(code, entities)

        self.assertEqual(result.content, code.replace("https://buy.stripe.com/6oE5npbGVbhC97afZ4", "https://buy.stripe.com/00g5npeT71H2gzCfZ8"))
        self.assertEqual(result.code_change_description, "")
        self.assertEqual(result.file_path, file_path)

    @patch("sweepai.agents.graph_child.extract_python_span")
    def test_code_plan_extraction_with_entities(self, mock_extract):
        code = "print('Hello, world!')"
        file_path = "test.py"
        entities = ["Hello"]
        issue_metadata = "Test issue"
        previous_snippets = "Test snippets"
        all_symbols_and_files = "Test symbols and files"

        mock_extract.return_value = "Test snippet"

        result = self.bot.code_plan_extraction(
            code,
            file_path,
            entities,
            issue_metadata,
            previous_snippets,
            all_symbols_and_files,
        )

        mock_extract.assert_called_once_with(code, entities)
        self.assertEqual(result.relevant_new_snippet, "Test snippet")
        self.assertEqual(result.code_change_description, "")
        self.assertEqual(result.file_path, file_path)

    def test_extract_python_span_no_entities(self):
        code = "print('Hello, world!')"
        entities = None

        result = extract_python_span(code, entities)

        self.assertEqual(result.content, code)

    def test_extract_python_span_with_entities(self):
        code = "print('Hello, world!')"
        entities = ["Hello"]

        result = extract_python_span(code, entities)

        self.assertIn(entities[0], result.content.replace("https://buy.stripe.com/6oE5npbGVbhC97afZ4", "https://buy.stripe.com/00g5npeT71H2gzCfZ8"))


if __name__ == "__main__":
    unittest.main()
