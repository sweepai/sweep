import unittest
from unittest.mock import patch, MagicMock
from loguru import logger

from sweepai.utils.github_utils import (
    make_valid_string,
    get_jwt,
    get_token,
    get_github_client,
    get_installation_id,
    ClonedRepo,
    get_file_names_from_query,
    get_hunks,
)


class TestGithubUtils(unittest.TestCase):
    @patch("re.sub")
    def test_make_valid_string(self, mock_sub):
        make_valid_string("test_string")
        mock_sub.assert_called_once_with(r"[^\w./-]+", "_", "test_string")

    @patch("jwt.encode")
    def test_get_jwt(self, mock_encode):
        get_jwt()
        mock_encode.assert_called_once()

    @patch("requests.post")
    @patch("time.time")
    def test_get_token(self, mock_time, mock_post):
        mock_time.return_value = 0
        get_token(123)
        mock_post.assert_called_once()

    @patch("github.Github")
    def test_get_github_client(self, mock_github):
        get_github_client(123)
        mock_github.assert_called_once()

    @patch("requests.get")
    def test_get_installation_id(self, mock_get):
        get_installation_id("username")
        mock_get.assert_called_once()

    @patch("os.path.exists")
    @patch("git.Repo")
    def test_cloned_repo(self, mock_repo, mock_exists):
        mock_exists.return_value = True
        cloned_repo = ClonedRepo("repo_full_name", "installation_id")
        mock_repo.assert_called()

    @patch("re.findall")
    def test_get_file_names_from_query(self, mock_findall):
        get_file_names_from_query("query")
        mock_findall.assert_called_once_with(r"\b[\w\-\.\/]*\w+\.\w{1,6}\b", "query")

    @patch("difflib.Differ", return_value=MagicMock())
    def test_get_hunks(self, mock_differ):
        mock_differ.return_value.compare.return_value = ["+ line1", "- line2"]
        result = get_hunks("str1", "str2", 1)
        mock_differ.assert_called_once()
        self.assertEqual(result, "+ line1\n- line2")

if __name__ == "__main__":
    unittest.main()
