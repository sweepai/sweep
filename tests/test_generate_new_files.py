import unittest
from unittest.mock import patch, mock_open
from sweep import generate_new_files

class TestGenerateNewFiles(unittest.TestCase):
    @patch('builtins.open', new_callable=mock_open, read_data="data")
    def test_read_exclude_file(self, mock_file):
        result = generate_new_files.read_exclude_file()
        self.assertEqual(result, "data")

    @patch('sweep.generate_new_files.sweep_config')
    def test_update_sweep_config(self, mock_sweep_config):
        generate_new_files.update_sweep_config("data")
        mock_sweep_config.update.assert_called_with("data")
</new_file>

