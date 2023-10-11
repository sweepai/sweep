import unittest

from sweepai.agents.graph_child import GraphChildBot, GraphContextAndPlan


class TestGraphChild(unittest.TestCase):
    def test_graph_child_bot(self):
        bot = GraphChildBot()
        code = "test code"
        file_path = "test_file_path"
        entities = "test_entities"
        issue_metadata = "test_issue_metadata"
        previous_snippets = "test_previous_snippets"
        all_symbols_and_files = "test_all_symbols_and_files"

        result = bot.code_plan_extraction(
            code,
            file_path,
            entities,
            issue_metadata,
            previous_snippets,
            all_symbols_and_files,
        )

        self.assertIsInstance(result, GraphContextAndPlan)
        self.assertEqual(result.file_path, file_path)

    def test_graph_context_and_plan(self):
        string = "test_string"
        file_path = "test_file_path"

        result = GraphContextAndPlan.from_string(string, file_path)

        self.assertIsInstance(result, GraphContextAndPlan)
        self.assertEqual(result.file_path, file_path)


if __name__ == "__main__":
    unittest.main()
