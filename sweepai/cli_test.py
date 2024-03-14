import json
import os
import unittest
from unittest.mock import mock_open, patch

from sweepai.cli import load_config, run


class TestConfigLoading(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=json.dumps(
            {"GITHUB_PAT": "test_github_pat", "OPENAI_API_KEY": "test_openai_key"}
        ),
    )
    def test_load_config(self, mock_file, mock_exists):
        with self.assertRaises(KeyError):
            os.environ["GITHUB_PAT"]
        with self.assertRaises(KeyError):
            os.environ["OPENAI_API_KEY"]
        load_config()
        self.assertEqual(os.environ["GITHUB_PAT"], "test_github_pat")
        self.assertEqual(os.environ["OPENAI_API_KEY"], "test_openai_key")


class TestCLIRunIsssue(unittest.TestCase):
    @patch("os.path.exists", return_value=False)
    def test_run_issue_no_config(self, mock_exists):
        with self.assertRaises(ValueError):
            run("https://github.com/sweepai/e2e/issues/1")


if __name__ == "__main__":
    unittest.main()
