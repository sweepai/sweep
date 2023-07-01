import unittest
from unittest import mock
from generate_new_files import read_exclude_file_from_repo_root

class TestGenerateNewFiles(unittest.TestCase):
    @mock.patch('generate_new_files.read_exclude_file_from_repo_root')
    def test_read_exclude_file_exists(self, mock_read):
        mock_read.return_value = ['expected', 'results']
        result = read_exclude_file_from_repo_root()
        self.assertEqual(result, ['expected', 'results'])

    @mock.patch('generate_new_files.read_exclude_file_from_repo_root')
    def test_read_exclude_file_not_exists(self, mock_read):
        mock_read.return_value = []
        result = read_exclude_file_from_repo_root()
        self.assertEqual(result, [])

    @mock.patch('generate_new_files.read_exclude_file_from_repo_root')
    def test_read_exclude_file_exception_handling(self, mock_read):
        mock_read.side_effect = Exception('error')
        with self.assertRaises(Exception):
            read_exclude_file_from_repo_root()

if __name__ == '__main__':
    unittest.main()

