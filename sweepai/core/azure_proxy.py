import os
import openai
import requests

class AzureProxy:
    def __init__(self):
        self.gpt35_key = os.getenv('GPT35_AZURE_KEY')
        self.gpt4_key = os.getenv('GPT4_AZURE_KEY')
        self.gpt4_32k_key = os.getenv('GPT4_32K_AZURE_KEY')
        self.api_type = os.getenv('OPENAI_API_TYPE')
        self.api_base = os.getenv('OPENAI_API_BASE')
        self.api_version = os.getenv('OPENAI_API_VERSION')

    def set_keys(self, gpt35_key, gpt4_key, gpt4_32k_key):
        self.gpt35_key = gpt35_key
        self.gpt4_key = gpt4_key
        self.gpt4_32k_key = gpt4_32k_key

    def call_openai(self, model, message):
        if model == 'gpt3.5':
            key = self.gpt35_key
        elif model == 'gpt4':
            key = self.gpt4_key
        elif model == 'gpt4-32k':
            key = self.gpt4_32k_key
        else:
            raise ValueError('Invalid model')

        headers = {'Authorization': f'Bearer {key}'}
        data = {'messages': message}
        response = requests.post(f'{self.api_base}/v1/engines/{model}/completions', headers=headers, json=data)

        if response.status_code != 200 and os.getenv('OPENAI_FALLBACK') == 'true':
            openai.api_key = os.getenv('OPENAI_API_KEY')
            response = openai.Completion.create(engine=model, prompt=message)

        return response.json()
