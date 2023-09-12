import os
import openai
from sweepai.config.server import OPENAI_API_TYPE, OPENAI_API_ENGINE

class OpenAIProxy:
    def __init__(self, OPENAI_API_KEY_GPT35, OPENAI_API_KEY_GPT4, OPENAI_API_KEY_GPT4_32K, OPENAI_FALLBACK):
        self.OPENAI_API_KEY_GPT35 = OPENAI_API_KEY_GPT35
        self.OPENAI_API_KEY_GPT4 = OPENAI_API_KEY_GPT4
        self.OPENAI_API_KEY_GPT4_32K = OPENAI_API_KEY_GPT4_32K
        self.OPENAI_FALLBACK = OPENAI_FALLBACK

    def call_openai(self, model, **kwargs):
        try:
            if model == 'gpt3.5' and OPENAI_API_TYPE == "azure" and self.OPENAI_API_KEY_GPT35 is not None:
                openai.api_key = self.OPENAI_API_KEY_GPT35
            elif model == 'gpt4' and OPENAI_API_TYPE == "azure" and self.OPENAI_API_KEY_GPT4 is not None:
                openai.api_key = self.OPENAI_API_KEY_GPT4
            elif model == 'gpt4-32k' and OPENAI_API_TYPE == "azure" and self.OPENAI_API_KEY_GPT4_32K is not None:
                openai.api_key = self.OPENAI_API_KEY_GPT4_32K
    
            response = openai.ChatCompletion.create(
                engine=OPENAI_API_ENGINE if OPENAI_API_TYPE == "azure" else None,
                model=model,
                messages=kwargs.get('messages'),
                max_tokens=kwargs.get('max_tokens'),
                temperature=kwargs.get('temperature'),
                functions=kwargs.get('functions'),
                function_call=kwargs.get('function_call'),
            ).choices[0].message
            return response
        except Exception as e:
            if self.OPENAI_FALLBACK and OPENAI_API_TYPE == "azure" and self.OPENAI_API_KEY_GPT35 is not None:
                openai.api_key = self.OPENAI_API_KEY_GPT35
                response = openai.ChatCompletion.create(model='gpt-3.5-turbo', **kwargs)
                return response
            else:
                raise e
