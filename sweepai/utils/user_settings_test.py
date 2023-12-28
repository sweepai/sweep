import unittest
from unittest.mock import MagicMock, patch

from sweepai.utils.user_settings import UserSettings


class UserSettingsTest(unittest.TestCase):
    @patch('sweepai.utils.user_settings.global_mongo_client')
    @patch('sweepai.utils.user_settings.Github')
    def setUp(self, mock_github, mock_mongo_client):
        self.mock_collection = MagicMock()
        mock_mongo_client.__getitem__.return_value = {'users': self.mock_collection}
        self.mock_github = mock_github

    def test_from_username_exists_in_db(self):
        self.mock_collection.find_one.return_value = {'username': 'testuser', 'email': 'testuser@example.com'}
        user_settings = UserSettings.from_username('testuser')
        self.assertEqual(user_settings.username, 'testuser')
        self.assertEqual(user_settings.email, 'testuser@example.com')

    def test_from_username_exists_on_github(self):
        self.mock_collection.find_one.return_value = None
        self.mock_github.return_value.get_user.return_value.email = 'testuser@example.com'
        user_settings = UserSettings.from_username('testuser')
        self.assertEqual(user_settings.username, 'testuser')
        self.assertEqual(user_settings.email, 'testuser@example.com')

    def test_from_username_not_exists(self):
        self.mock_collection.find_one.return_value = None
        self.mock_github.return_value.get_user.return_value.email = None
        user_settings = UserSettings.from_username('testuser')
        self.assertEqual(user_settings.username, 'testuser')
        self.assertEqual(user_settings.email, '')

if __name__ == '__main__':
    unittest.main()
