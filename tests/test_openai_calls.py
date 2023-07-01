tests/test_openai_calls.py
</new_file>

```python
import unittest
from unittest.mock import patch, Mock
from sweepai.core.openai_calls import get_openai_response

class TestOpenAICalls(unittest.TestCase):
    @patch('sweepai.core.openai_calls.openai.ChatCompletion.create')
    def test_get_openai_response(self, mock_create):
        # Mock the OpenAI API response
        mock_response = Mock()
        mock_response.choices = [{'message': {'role': 'system', 'content': 'Test response'}}]
        mock_create.return_value = mock_response

        # Call the function with a test prompt
        response = get_openai_response('Test prompt')

        # Check that the API was called with the correct arguments
        mock_create.assert_called_once_with(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": 'Test prompt'}
            ]
        )

        # Check that the function returned the correct response
        self.assertEqual(response, 'Test response')

if __name__ == "__main__":
    unittest.main()
