import openai

class OpenAIProxy:
    def __init__(self, azure_keys, fallback):
        self.azure_keys = azure_keys
        self.fallback = fallback

    def call_openai(self, model, **kwargs):
        try:
            openai.api_key = self.azure_keys[model]
            response = openai.ChatCompletion.create(model=model, **kwargs)
            return response
        except Exception as e:
            if self.fallback:
                openai.api_key = self.azure_keys['openai']
                response = openai.ChatCompletion.create(model='gpt-3.5-turbo', **kwargs)
                return response
            else:
                raise e
