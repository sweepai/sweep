import unittest
from unittest.mock import Mock

from sweepai.utils import ticket_utils


class TestTicketUtils(unittest.TestCase):
    def test_fire_and_forget_wrapper(self):
        # Create a mock function
        mock_function = Mock()

        # Call fire_and_forget_wrapper with the mock function
        wrapped_function = ticket_utils.fire_and_forget_wrapper(mock_function)

        # Call the wrapped function
        wrapped_function()

        # Assert that the mock function was called
        mock_function.assert_called_once()
