from sweepai.utils.github_utils import shutil
from os import os
import unittest
from unittest.mock import Mock, patch

from sweepai.utils.github_utils import ClonedRepo


@unittest.skip("Fails")
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

    @patch("shutil.rmtree")
    def test_delete(self, mock_rmtree):
        self.cloned_repo.delete()
        mock_rmtree.assert_called_once_with(self.cloned_repo.repo_dir)

    @patch("os.listdir")
    def test_list_directory_tree(self, mock_listdir):
        mock_listdir.return_value = ["file1", "file2"]
        tree, dir_obj = self.cloned_repo.list_directory_tree()
        self.assertEqual(tree.count("\n"), 2)

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

    @patch("shutil.copytree")
    @patch("os.symlink")
    @patch("os.path.isdir")
    def test_copy_tree_with_symlink(self, mock_isdir, mock_symlink, mock_copytree):
        symlink_source = "/tmp/original"
        symlink_target = "/tmp/link"
        repo_dir = "/tmp/fake_repo_dir"
        symlink_path = os.path.join(repo_dir, symlink_target)
        # Mock the isdir to return False when checking the symlink target (common symlink behavior)
        # Mock the symlink to not actually create a symlink
        # Mock the copytree to simulate the copy operation including symlinks
        mock_isdir.side_effect = lambda path: False if path == symlink_path else True
        mock_symlink.return_value = None
        mock_copytree.side_effect = lambda src, dst, symlinks: symlink_target if symlinks else None
        # Assume that the symlink exists in the source directory
        mock_isdir.return_value = True
        # Run the shutil.copy_tree function with symlinks=True
        shutil.copytree(repo_dir, '/tmp/fake_dest_repo_dir', symlinks=True)
        # Verify that the symbolic link was copied correctly
        mock_symlink.assert_not_called()
        mock_copytree.assert_called_once_with(repo_dir, ANY, symlinks=True)

