import requests
import json
from sweepai.core.chat import ChatGPT

def handle_comment(comment_text):
    # Initialize the chatbot
    chatbot = ChatGPT()

    # Determine the appropriate response
    response = chatbot.generate_response(comment_text)

    # Post the response to GitHub
    url = "https://api.github.com/repos/sweepai/sweep/issues/comments"
    headers = {"Authorization": "token YOUR_GITHUB_TOKEN"}
    data = {"body": response}
    response = requests.post(url, headers=headers, data=json.dumps(data))

    # Check for errors
    respo

