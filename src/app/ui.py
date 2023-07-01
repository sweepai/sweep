import json
import gradio as gr
from loguru import logger
import modal

from src.app.backend import APIClient
from src.app.config import Config
from src.core.entities import Snippet
from src.utils.constants import DB_NAME

get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")
config = Config.load()
# repo_name = "sweepai/sweep"
# username = "kevinlu1248"
username = config.github_username
installation_id = 35473183

api_client = APIClient()

pr_summary_template = """💡 I'll create the following PR:

**{title}**
{summary}

Here is my plan:
{plan}

Reply with "ok" to create the PR or anything else to propose changes."""

with gr.Blocks(theme=gr.themes.Soft(), title="Sweep Chat", css="footer {{visibility: hidden;}}") as demo:
    repo_name = gr.Textbox(label="Repo full name",)
    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=650)
        with gr.Column():
            # table = gr.Dataframe([("", "")], headers=["Snippet", "Preview"], label="Relevant Snippets")
            snippets_text = gr.Markdown(value="### Relevant snippets", max_height=750)
    msg = gr.Textbox(label="Message to Sweep",)
    clear = gr.ClearButton([msg, chatbot, snippets_text])

    snippets: list[Snippet] = []
    proposed_pr: str | None = None

    def user(user_message: str, history: list[tuple[str | None, str | None]]):
        return gr.update(value="", interactive=False), history + [[user_message, None]]

    def bot(chat_history: list[tuple[str | None, str | None]], snippets_text):
        snippets = []
        yield chat_history, snippets_text
        if snippets_text and snippets_text.strip().count("\n") == 0:
            # Searching for relevant snippets
            chat_history[-1][1] = "Searching for relevant snippets..."
            yield chat_history, snippets_text
            logger.info("Fetching relevant snippets...")
            snippets = api_client.search(repo_name, chat_history[-1][0], 5, installation_id)
            logger.info("Fetched relevant snippets.")
            chat_history[-1][1] = "Found relevant snippets."
            
            backtick, escaped_backtick = "`", "\\`"
            snippets_text = "### Relevant snippets:\n" + "\n".join([f"{snippet.denotation}\n```python\n{snippet.get_preview(10).replace(backtick, escaped_backtick)}\n```" for snippet in snippets])
            yield chat_history, snippets_text
        
        global proposed_pr
        if proposed_pr and chat_history[-1][0].strip().lower() in ("okay", "ok"):
            chat_history[-1][1] = f"⏳ Creating PR..."
            yield chat_history, snippets_text
            pull_request = api_client.create_pr(
                file_change_requests=[(item["file_path"], item["instructions"]) for item in proposed_pr["plan"]],
                pull_request={
                    "title": proposed_pr["title"],
                    "content": proposed_pr["summary"],
                    "branch_name": proposed_pr["branch"],
                },
                messages=chat_history,
                repo_name=repo_name,
                username=username,
                installation_id=installation_id
            )
            chat_history[-1][1] = f"✅ PR created at {pull_request['html_url']}"
            yield chat_history, snippets_text
            return

        # Generate response
        logger.info("Fetching endpoint...")
        chat_history.append([None, "Fetching endpoint..."])
        yield chat_history, snippets_text
        chat_history[-1][1] = ""
        logger.info("Starting to generate response...")
        stream = api_client.stream_chat(chat_history, snippets)
        function_name = ""
        raw_arguments = ""
        for chunk in stream:
            if chunk.get("content"):
                token = chunk["content"]
                chat_history[-1][1] += token
                yield chat_history, snippets_text
            if chunk.get("function_call"):
                function_call = chunk["function_call"]
                function_name = function_name or function_call.get("name")
                raw_arguments += function_call.get("arguments")
                chat_history[-1][1] = f"Calling function: `{function_name}`\n```json\n{raw_arguments}\n```"
                yield chat_history, snippets_text
        if function_name:
            arguments = json.loads(raw_arguments)
            if function_name == "create_pr":
                assert "title" in arguments
                assert "summary" in arguments
                assert "plan" in arguments
                if "branch" not in arguments:
                    arguments["branch"] = arguments["title"].lower().replace(" ", "_").replace("-", "_")[:50]
                chat_history[-1][1] = pr_summary_template.format(
                    title=arguments["title"],
                    summary=arguments["summary"],
                    plan="\n".join([f"* `{item['file_path']}`: {item['instructions']}" for item in arguments["plan"]])
                )
                yield chat_history, snippets_text
                proposed_pr = arguments
            else:
                raise NotImplementedError

    response = msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(bot, [chatbot, snippets_text], [chatbot, snippets_text])
    response.then(lambda: gr.update(interactive=True), None, [msg], queue=False)


if __name__ == "__main__":
    demo.queue()
    demo.launch()
