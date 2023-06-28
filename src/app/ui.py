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

with gr.Blocks(theme="dark") as demo:
    chatbot = gr.Chatbot(height=800)
    msg = gr.Textbox()
    clear = gr.ClearButton([msg, chatbot])

    def user(user_message, history):
        return gr.update(value="", interactive=False), history + [[user_message, None]]

    def bot(chat_history):
        chat_history[-1][1] = "Searching for relevant snippets..."
        yield chat_history
        logger.info("Fetching relevant snippets...")
        snippets = api_client.search(repo_name, chat_history[-1][0], 5, installation_id)
        logger.info("Fetched relevant snippets.")
        bot_message = "Some relevant snippets I found:\n\n"
        bot_message += "\n".join(f"{snippet.get_markdown_link(repo_name)}\n```{snippet.get_preview()}\n```" for snippet in snippets)
        chat_history[-1][1] = ""
        for character in bot_message:
            chat_history[-1][1] += character
            yield chat_history

    response = msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
        bot, chatbot, chatbot
    )
    response.then(lambda: gr.update(interactive=True), None, [msg], queue=False)


demo.queue()
demo.launch()