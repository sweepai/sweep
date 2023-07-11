import unittest
from sweepai.app.backend import verify_config, installation_id, search, create_pr, chat, chat_stream

class TestBackend(unittest.TestCase):

    def test_verify_config(self):
        result = verify_config(input)
        self.assertEqual(result, expected_result)

    def test_installation_id(self):
        result = installation_id(input)
        self.assertEqual(result, expected_result)

    def test_search(self):
        result = search(input)
        self.assertEqual(result, expected_result)

    def test_create_pr(self):
        result = create_pr(input)
        self.assertEqual(result, expected_result)

    def test_chat(self):
        result = chat(input)
        self.assertEqual(result, expected_result)

    def test_chat_stream(self):
        result = chat_stream(input)
        self.assertEqual(result, expected_result)

if __name__ == '__main__':
    unittest.main()
