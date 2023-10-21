import unittest
from unittest.mock import patch, MagicMock
import os
import tempfile
from sweepai.utils.github_utils import ClonedRepo

class TestClonedRepo(unittest.TestCase):

    @patch("git.Repo.clone_from")
    def test_clone(self, mock_clone_from):
        cloned_repo = ClonedRepo(repo_full_name="test/repo", installation_id="123")
        cloned_repo.clone()
        mock_clone_from.assert_called_once_with(cloned_repo.clone_url, cloned_repo.cache_dir)

    def test_get_file_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_name = "test_file.txt"
            file_contents = "Hello, World!"
            with open(os.path.join(temp_dir, file_name), "w") as temp_file:
                temp_file.write(file_contents)

            cloned_repo = ClonedRepo(repo_full_name="test/repo", installation_id="123")
            cloned_repo.cache_dir = temp_dir
            self.assertEqual(cloned_repo.get_file_contents(file_name), file_contents)

    @patch("os.remove")
    def test_delete(self, mock_remove):
        cloned_repo = ClonedRepo(repo_full_name="test/repo", installation_id="123")
        cloned_repo.delete()
        mock_remove.assert_called_once_with(cloned_repo.cache_dir)
    
    @patch("os.path.exists")
    def test_exists(self, mock_exists):
        cloned_repo = ClonedRepo(repo_full_name="test/repo", installation_id="123")
        cloned_repo.exists()
        mock_exists.assert_called_once_with(cloned_repo.cache_dir)

if __name__ == "__main__":
    unittest.main()
