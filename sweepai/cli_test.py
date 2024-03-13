# import unittest
# from unittest.mock import patch, mock_open

# class TestConfigLoading(unittest.TestCase):
#     @patch('os.path.exists')
#     @patch('builtins.open', new_callable=mock_open, read_data='{"GITHUB_PAT": "test", "OPENAI_API_KEY": "test"}')
#     def test_load_config(self, mock_file, mock_exists):
#         mock_exists.return_value = True
#         # Your function to load config here, e.g., load_config()
#         # Assert the configuration has been loaded correctly
#         self.assertEqual(config['GITHUB_PAT'], 'test')
#         self.assertEqual(config['OPENAI_API_KEY'], 'test')

# if __name__ == '__main__':
#     unittest.main()
