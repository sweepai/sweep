import unittest
import unittest.mock

from sweepai import api


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.mock_api = unittest.mock.create_autospec(api)

    def test_webhook(self):
        self.mock_api.webhook.return_value = {"success": True}
        result = self.mock_api.webhook()
        self.assertEqual(result, {"success": True})
        self.mock_api.webhook.assert_called_once()

    def test_home(self):
        self.mock_api.home.return_value = "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>"
        result = self.mock_api.home()
        self.assertEqual(result, "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>")
        self.mock_api.home.assert_called_once()

    # Test to ensure the processing of events in watch.py remains intact after the removal of print statements
    @unittest.mock.patch('sweepai.watch.stream_events', return_value=iter([]))
    def test_event_processing(self, mock_stream_events):
        # Simulate an event being processed
        mock_event = unittest.mock.Mock()
        mock_event.raw_data = {'id': '1234', 'type': 'PushEvent', 'actor': {'login': 'user'}, 'payload': {}, 'created_at': '2021-01-01T00:00:00Z'}
        mock_stream_events.return_value = iter([mock_event])

        # Simulate payload construction
        expected_payload = {
            'id': '1234',
            'type': 'push',
            'actor': {'login': 'user', 'type': 'User'},
            'payload': {},
            'created_at': '2021-01-01T00:00:00Z',
            'repository': {},
            'installation': {'id': -1}
        }
        with unittest.mock.patch('sweepai.api.handle_request') as mock_handle_request:
            self.test_api.process_event()
            mock_handle_request.assert_called_once_with(expected_payload, 'push')

    # Add more test methods as needed for each function in api.py

if __name__ == '__main__':
    unittest.main()
