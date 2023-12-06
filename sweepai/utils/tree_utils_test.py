import os
import unittest

from sweepai.utils.tree_utils import DirectoryTree


class TestDirectoryTree(unittest.TestCase):
    def test_symlink_handling(self):
        # Create a temporary directory and a symbolic link within it
        os.mkdir("/tmp/test_dir")
        os.mkdir("/tmp/test_dir/target_dir")
        os.symlink("/tmp/test_dir/target_dir", "/tmp/test_dir/symlink")

        # Create a DirectoryTree instance and parse the temporary directory
        tree = DirectoryTree()
        tree.parse("/tmp/test_dir")

        # Verify that the symbolic link is correctly identified and handled
        self.assertIn("/tmp/test_dir/symlink", [line.full_path() for line in tree.lines])

        # Remove the symbolic link and verify that it is correctly removed
        tree.remove("/tmp/test_dir/symlink")
        self.assertNotIn("/tmp/test_dir/symlink", [line.full_path() for line in tree.lines])

        # Clean up the temporary directory and its contents
        os.remove("/tmp/test_dir/symlink")
        os.rmdir("/tmp/test_dir/target_dir")
        os.rmdir("/tmp/test_dir")

if __name__ == "__main__":
    unittest.main()
