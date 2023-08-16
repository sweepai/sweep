from translate import Translator
from sweepai.core.chat import ChatGPT

class ArabicChatBot(ChatGPT):
    def chat(self, content: str, model: ChatModel | None = None, message_key: str | None = None):
        # Translate user input from Arabic to English
        translator = Translator(from_lang='ar', to_lang='en')
        translated_input = translator.translate(content)

        # Process translated input using the existing chatbot logic
        response = super().chat(translated_input, model=model, message_key=message_key)

        # Translate response from English to Arabic before sending it to the user
        translator = Translator(from_lang='en', to_lang='ar')
        translated_response = translator.translate(response)
        return translated_response