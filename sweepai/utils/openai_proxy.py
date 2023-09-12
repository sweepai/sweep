import os
import openai

class OpenAIProxy:
    def __init__(self, OPENAI_API_KEY_GPT35, OPENAI_API_KEY_GPT4, OPENAI_API_KEY_GPT4_32K, OPENAI_FALLBACK):
        self.OPENAI_API_KEY_GPT35 = OPENAI_API_KEY_GPT35
        self.OPENAI_API_KEY_GPT4 = OPENAI_API_KEY_GPT4
        self.OPENAI_API_KEY_GPT4_32K = OPENAI_API_KEY_GPT4_32K
        self.OPENAI_FALLBACK = OPENAI_FALLBACK

    def call_openai(self, model, **kwargs):
        try:
            if model == 'gpt3.5':
                openai.api_key = self.OPENAI_API_KEY_GPT35
            elif model == 'gpt4':
                openai.api_key = self.OPENAI_API_KEY_GPT4
            elif model == 'gpt4-32k':
                openai.api_key = self.OPENAI_API_KEY_GPT4_32K
    
            response = openai.ChatCompletion.create(model=model, **kwargs)
            return response
        except Exception as e:
            if self.OPENAI_FALLBACK:
                openai.api_key = self.OPENAI_API_KEY_GPT35
                response = openai.ChatCompletion.create(model='gpt-3.5-turbo', **kwargs)
                return response
            else:
                raise e
