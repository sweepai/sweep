import time
import gradio as gr
from loguru import logger
import modal

from src.app.backend import APIClient
from src.utils.constants import DB_NAME

get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")
repo_name = "sweepai/sweep"
installation_id = 35473183

api_client = APIClient()

with gr.Blocks(theme=gr.themes.Soft()) as demo:
    chatbot = gr.Chatbot(height=750)
    msg = gr.Textbox()
    clear = gr.ClearButton([msg, chatbot])

    def user(user_message: str, history: list[tuple[str | None, str | None]]):
        return gr.update(value="", interactive=False), history + [[user_message, None]]

    def bot(chat_history: list[tuple[str | None, str | None]]):
        # Searching for relevant snippets
        chat_history[-1][1] = "Searching for relevant snippets..."
        yield chat_history
        logger.info("Fetching relevant snippets...")
        snippets = api_client.search(repo_name, chat_history[-1][0], 5, installation_id)
        logger.info("Fetched relevant snippets.")
        snippets_found = "Some relevant snippets I found:\n\n"
        snippets_found += "\n".join(f"{snippet.get_markdown_link(repo_name)}\n```python{snippet.get_preview()}\n```" for snippet in snippets)
        chat_history[-1][1] = ""
        for character in snippets_found:
            chat_history[-1][1] += character
            yield chat_history

        # Generate response
        logger.info("Generating response...")
        chat_history.append([None, "..."])
        yield chat_history
        chat_history[-1][1] = ""
        logger.info("Generated response.")
        stream = api_client.stream_chat(chat_history)
        for token in stream:
            chat_history[-1][1] += token
            yield chat_history

    response = msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
        bot, chatbot, chatbot
    )
    response.then(lambda: gr.update(interactive=True), None, [msg], queue=False)


demo.queue()
demo.launch()