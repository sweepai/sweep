import json
import time
import gradio as gr
from loguru import logger
import modal

from src.app.backend import APIClient
from src.core.entities import Snippet
from src.utils.constants import DB_NAME

get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")
repo_name = "sweepai/sweep"
installation_id = 35473183

api_client = APIClient()

with gr.Blocks(theme=gr.themes.Soft(), title="Sweep Chat", css="footer {{visibility: hidden;}}") as demo:
    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=750)
        with gr.Column():
            table = gr.Dataframe([("", "")], headers=["Snippet", "Preview"], label="Relevant Snippets")
    msg = gr.Textbox()
    clear = gr.ClearButton([msg, chatbot, table])
    snippets: list[Snippet] = []

    def user(user_message: str, history: list[tuple[str | None, str | None]]):
        return gr.update(value="", interactive=False), history + [[user_message, None]]

    def bot(chat_history: list[tuple[str | None, str | None]], table):
        snippets = []
        if False: # len(table) == 0 or table.iloc[0][0] == "":
            # Searching for relevant snippets
            chat_history[-1][1] = "Searching for relevant snippets..."
            yield chat_history, table
            logger.info("Fetching relevant snippets...")
            snippets = api_client.search(repo_name, chat_history[-1][0], 5, installation_id)
            logger.info("Fetched relevant snippets.")
            chat_history[-1][1] = "Found relevant snippets."
            
            table = [(f"{snippet.file_path}:{snippet.start}:{snippet.end}", snippet.get_preview()) for snippet in snippets]
            yield chat_history, table

        # Generate response
        logger.info("Fetching endpoint...")
        chat_history.append([None, "Fetching endpoint..."])
        yield chat_history, table
        chat_history[-1][1] = ""
        logger.info("Starting to generate response...")
        stream = api_client.stream_chat(chat_history, snippets)
        function_name = ""
        raw_arguments = ""
        for chunk in stream:
            if chunk.get("content"):
                token = chunk["content"]
                chat_history[-1][1] += token
                yield chat_history, table
            if chunk.get("function_call"):
                function_call = chunk["function_call"]
                function_name = function_name or function_call.get("name")
                raw_arguments += function_call.get("arguments")
                chat_history[-1][1] = f"Calling function: `{function_name}`\n```json\n{raw_arguments}\n```"
                yield chat_history, table
        if function_name:
            arguments = json.loads(raw_arguments)
            

    response = msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
        bot, [chatbot, table], [chatbot, table]
    )
    response.then(lambda: gr.update(interactive=True), None, [msg], queue=False)


demo.queue()
demo.launch()