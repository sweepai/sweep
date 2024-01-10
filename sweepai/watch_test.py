import unittest
from unittest.mock import Mock, patch

import pytest

from sweepai import watch


class TestWatch(unittest.TestCase):
    def setUp(self):
        self.mock_repo = Mock()
        self.watch = watch.Watch(self.mock_repo)

    @patch('time.sleep')
    def test_stream_events(self, mock_sleep):
        mock_event = Mock()
        self.mock_repo.get_events.return_value = [mock_event]
        self.mock_repo.get_issues_events.return_value = []

        events = list(self.watch.stream_events(timeout=1, offset=1))

        self.assertEqual(events, [mock_event])
        mock_sleep.assert_called_once_with(1)

    @patch('time.sleep')
    def test_payload_construction(self, mock_sleep):
        mock_event = Mock()
        mock_event.raw_data = {'key': 'value'}
        mock_event.payload = {'payload_key': 'payload_value'}
        self.mock_repo.get_events.return_value = [mock_event]
        self.mock_repo.get_issues_events.return_value = []

        events = list(self.watch.stream_events(timeout=1, offset=1))
        payload = events[0].payload

        self.assertEqual(payload, {'key': 'value', 'payload_key': 'payload_value'})

if __name__ == '__main__':
    unittest.main()
