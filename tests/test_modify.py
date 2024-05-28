import os
import unittest
from unittest.mock import MagicMock, patch

from sweepai.agents.modify import modify
from sweepai.core.entities import FileChangeRequest
from sweepai.utils.github_utils import ClonedRepo


class TestModify(unittest.TestCase):
    def setUp(self):
        self.repo_mock = MagicMock(spec=ClonedRepo)
        self.repo_mock.repo_dir = "/path/to/repo"
        self.repo_mock.get_file_contents.return_value = "original content"

    def test_simple_modification(self):
        fcr = FileChangeRequest(
            filename="file1.txt",
            instructions="<original_code>original content</original_code><new_code>modified content