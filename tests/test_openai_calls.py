import unittest
import openai

class TestOpenAICalls(unittest.TestCase):

    def setUp(self):
        self.api_key = 'your-api-key'
        openai.api_key = self.api_key

    def test_openai_call(self):
        response = openai.Completion.create(
          engine="davinci-codex",
          prompt="Translate these English words to French: {\"Hello\": \"\", \"World\": \"\"}",
          temperature=0.5,
          max_tokens=60
        )
        self.assertIsNotNone(response)

    def test_openai_call_failure(self):
        with self.assertRaises(Exception):
            response = openai.Completion.create(
              engine="davinci-codex",
              prompt="Translate these English words to French: {\"Hello\": \"\", \"World\": \"\"}",
              temperature=0.5,
              max_tokens=6000
            )

if __name__ == '__main__':
    unittest.main()
