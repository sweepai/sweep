import unittest
from test import a_func
from unittest.mock import patch


class TestAFunc(unittest.TestCase):
    @patch("builtins.print")
    def test_a_func(self, mock_print):
        a_func()
        mock_print.assert_called_once_with(2, 8)
