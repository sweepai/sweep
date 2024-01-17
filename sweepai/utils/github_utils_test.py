from sandbox.src.sandbox_local import cloned_repo
import unittest
from unittest.mock import Mock, patch

from sweepai.utils.github_utils import ClonedRepo


class TestClonedRepo(unittest.TestCase):
    def setUp(self):
        self.repo_full_name = "sweepai/sweep"
        self.installation_id = "12345"
        self.branch = "main"
        self.token = "mock_token"
        self.cloned_repo = ClonedRepo(
            repo_full_name=self.repo_full_name,
            installation_id=self.installation_id,
            branch=self.branch,
            token=self.token,
        )

    @patch("os.path.exists")
    @patch("git.Repo")
    def test_post_init(self, mock_repo, mock_exists):
        mock_exists.return_value = True
        self.cloned_repo.__post_init__()
        mock_repo.assert_called_once()

    @patch("os.listdir")
    def test_list_directory_tree(self, mock_listdir):
        mock_listdir.return_value = ["file1", "file2"]
        tree, dir_obj = self.cloned_repo.list_directory_tree()
        self.assertEqual(tree.count("\n"), 2)

    @patch("shutil.rmtree")
    @patch("os.remove")
    def test_del_method(self, mock_remove, mock_rmtree):
        cloned_repo = ClonedRepo(
            repo_full_name=self.repo_full_name,
            installation_id=self.installation_id,
            branch=self.branch,
            token=self.token,
        )
        # Explicitly call __del__ to trigger cleanup or let the object go out of scope
        del cloned_repo
        mock_rmtree.assert_called_once_with(cloned_repo.repo_dir)
        mock_remove.assert_called_once_with(cloned_repo.zip_path)
        mock_rmtree.side_effect = Exception('rmtree error')
        mock_remove.side_effect = Exception('remove error')
        try:
            del cloned_repo
            rmtree_called = True
        except Exception:
            rmtree_called = False
        self.assertTrue(rmtree_called)
        try:
            del cloned_repo
            remove_called = True
        except Exception:
            remove_called = False
        self.assertTrue(remove_called)

    @patch("os.listdir")
    def test_get_file_list(self, mock_listdir):
        mock_listdir.return_value = ["file1", "file2"]
        files = self.cloned_repo.get_file_list()
        self.assertEqual(len(files), 2)

    @patch("os.path.join")
    @patch("builtins.open")
    def test_get_file_contents(self, mock_open, mock_join):
        mock_join.return_value = "/tmp/cache/repos/sweepai/sweep/main/file1"
        mock_open.return_value.__enter__.return_value.read.return_value = "file content"
        content = self.cloned_repo.get_file_contents("file1")
        self.assertEqual(content, "file content")

    @patch("git.Repo")
    def test_get_num_files_from_repo(self, mock_repo):
        mock_repo.git.checkout.return_value = None
        self.cloned_repo.git_repo = mock_repo
        self.cloned_repo.get_file_list = Mock(return_value=["file1", "file2"])
        num_files = self.cloned_repo.get_num_files_from_repo()
        self.assertEqual(num_files, 2)

    @patch("git.Repo")
    def test_get_commit_history(self, mock_repo):
        mock_repo.iter_commits.return_value = ["commit1", "commit2"]
        self.cloned_repo.git_repo = mock_repo
        commit_history = self.cloned_repo.get_commit_history()
        self.assertEqual(len(commit_history), 2)
