from googletrans import Translator
from sweepai.core.chat import ChatGPT

class ArabicChatBot(ChatGPT):
    def chat(self, content: str, model: ChatModel | None = None, message_key: str | None = None):
        # Translate user input from Arabic to English
        translator = Translator()
        translated_input = translator.translate(content, src='ar', dest='en').text

        # Process translated input using the existing chatbot logic
        response = super().chat(translated_input, model=model, message_key=message_key)

        # Translate response from English to Arabic before sending it to the user
        translated_response = translator.translate(response, src='en', dest='ar').text
        return translated_response
