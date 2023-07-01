import unittest
import openai


class TestOpenAICalls(unittest.TestCase):
    def setUp(self):
        self.prompt = 'Translate the following English text to French: {\"text\": \"Hello, World!\"}'

    def test_chat_completion(self):
        response = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            messages=[
                {'role': 'system', 'content': 'You are a helpful assistant.'},
                {'role': 'user', 'content': self.prompt}
            ]
        )
        self.assertIsNotNone(response.choices)

    def test_completion(self):
        response = openai.Completion.create(
            engine='text-davinci-002',
            prompt=self.prompt,
            max_tokens=60
        )
        self.assertIsNotNone(response.choices)

if __name__ == '__main__':
    unittest.main()
</new_file>
