import json
from github import Github
import gradio as gr
from loguru import logger
import webbrowser

from sweepai.app.api_client import APIClient, create_pr_function, create_pr_function_call
from sweepai.app.config import SweepChatConfig
from sweepai.core.entities import Snippet
from sweepai.utils.constants import DB_NAME
from sweepai.utils.github_utils import get_files_recursively

config = SweepChatConfig.load()

api_client = APIClient(config=config)

pr_summary_template = """💡 I'll create the following PR:

**{title}**
{summary}

Here is my plan:
{plan}

Reply with "ok" to create the PR or anything else to propose changes."""

github_client = Github(config.github_pat)
repos = list(github_client.get_user().get_repos())

css = """
footer {
    visibility: hidden;
}
pre, code {
    white-space: pre-wrap !important;
    word-break: break-all !important;
}
#snippets {
    height: 750px;
    overflow-y: scroll;
}
"""

with gr.Blocks(theme=gr.themes.Soft(), title="Sweep Chat", css=css) as demo:
    with gr.Row():
        with gr.Column():
            repo_full_name = gr.Dropdown(choices=[repo.full_name for repo in repos], label="Repo full name", value=config.repo_full_name or "")
        with gr.Column(scale=2):
            repo = github_client.get_repo(config.repo_full_name)
            all_files, path_to_contents = get_files_recursively(repo)
            file_names = gr.Dropdown(choices=all_files, multiselect=True, label="Files")
    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=750)
        with gr.Column():
            snippets_text = gr.Markdown(value="### Relevant snippets", elem_id="snippets")
    msg = gr.Textbox(label="Message to Sweep", placeholder="Write unit tests for OpenAI calls")
    # clear = gr.ClearButton([msg, chatbot, snippets_text])

    proposed_pr: str | None = None
    searched = False
    selected_snippets = []
    file_to_str = {}

    def repo_name_change(repo_full_name):
        global installation_id
        try:
            config.repo_full_name = repo_full_name
            api_client.config = config
            installation_id = api_client.get_installation_id()
            assert installation_id
            config.installation_id = installation_id
            api_client.config = config
            config.save()
            return ""
        except Exception as e:
            webbrowser.open_new_tab("https://github.com/apps/sweep-ai")
            config.repo_full_name = None
            config.installation_id = None
            config.save()
            api_client.config = config
            raise e

    repo_full_name.change(repo_name_change, [repo_full_name], [msg])

    def build_string():
        global selected_snippets
        global file_to_str
        for snippet in selected_snippets:
            file_name = snippet.file_path
            if file_name not in file_to_str:
                add_file_to_dict(file_name)
        snippets_text = "### Relevant snippets:\n" + "\n\n".join([file_to_str[snippet.file_path] for snippet in selected_snippets])
        return snippets_text

    def add_file_to_dict(file_name):
        global file_to_str
        global path_to_contents
        if file_name in path_to_contents:
            file_contents = path_to_contents[file_name]
        else:
            file_contents = repo.get_contents(file_name).decoded_content.decode('utf-8')
        file_contents_split = file_contents.split("\n")
        length = len(file_contents_split)
        backtick, escaped_backtick = "`", "\\`"
        preview = "\n".join(file_contents_split[:3]).replace(backtick, escaped_backtick)
        file_to_str[file_name] = f'{file_name}:0:{length}\n```python\n{preview}\n...\n```'
    
    def file_names_change(file_names):
        global selected_snippets
        global file_to_str
        global path_to_contents
        selected_snippets = [Snippet(content=path_to_contents[file_name], start=0, end=path_to_contents[file_name].count('\n'), file_path=file_name) for file_name in file_names]
        return file_names, build_string()
    
    file_names.change(file_names_change, [file_names], [file_names, snippets_text])
    
    def handle_message_submit(repo_full_name: str, user_message: str, history: list[tuple[str | None, str | None]]):
        if not repo_full_name:
            raise Exception("Set the repository name first")
        return gr.update(value="", interactive=False), history + [[user_message, None]]

    def handle_message_stream(chat_history: list[tuple[str | None, str | None]], snippets_text, file_names):
        global selected_snippets
        global searched
        message = chat_history[-1][0]
        yield chat_history, snippets_text, file_names
        if not selected_snippets:
            searched = True
            # Searching for relevant snippets
            chat_history[-1][1] = "Searching for relevant snippets..."
            snippets_text = build_string()
            yield chat_history, snippets_text, file_names
            logger.info("Fetching relevant snippets...")
            selected_snippets += api_client.search(chat_history[-1][0], 3)
            snippets_text = build_string()
            file_names = [snippet.file_path for snippet in selected_snippets]
            yield chat_history, snippets_text, file_names
            logger.info("Fetched relevant snippets.")
            chat_history[-1][1] = "Found relevant snippets."
            # Update using chat_history
            snippets_text = build_string()
            yield chat_history, snippets_text, file_names
        
        global proposed_pr
        if proposed_pr and chat_history[-1][0].strip().lower() in ("okay", "ok"):
            chat_history[-1][1] = f"⏳ Creating PR..."
            yield chat_history, snippets_text, file_names
            pull_request = api_client.create_pr(
                file_change_requests=[(item["file_path"], item["instructions"]) for item in proposed_pr["plan"]],
                pull_request={
                    "title": proposed_pr["title"],
                    "content": proposed_pr["summary"],
                    "branch_name": proposed_pr["branch"],
                },
                messages=chat_history,
            )
            chat_history[-1][1] = f"✅ PR created at {pull_request['html_url']}"
            yield chat_history, snippets_text, file_names
            return

        # Generate response
        logger.info("...")
        chat_history.append([None, "..."])
        yield chat_history, snippets_text, file_names
        chat_history[-1][1] = ""
        logger.info("Starting to generate response...")
        if len(chat_history) > 1 and "create pr" in message.lower():
            stream = api_client.stream_chat(
                chat_history, 
                selected_snippets,
                functions=[create_pr_function],
                function_call=create_pr_function_call,
            )
        else:
            stream = api_client.stream_chat(chat_history, selected_snippets)
        function_name = ""
        raw_arguments = ""
        for chunk in stream:
            if chunk.get("content"):
                token = chunk["content"]
                chat_history[-1][1] += token
                yield chat_history, snippets_text, file_names
            if chunk.get("function_call"):
                function_call = chunk["function_call"]
                function_name = function_name or function_call.get("name")
                raw_arguments += function_call.get("arguments")
                chat_history[-1][1] = f"Calling function: `{function_name}`\n```json\n{raw_arguments}\n```"
                yield chat_history, snippets_text, file_names
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
                yield chat_history, snippets_text, file_names
                proposed_pr = arguments
            else:
                raise NotImplementedError

    response = msg.submit(handle_message_submit, [repo_full_name, msg, chatbot], [msg, chatbot], queue=False).then(handle_message_stream, [chatbot, snippets_text, file_names], [chatbot, snippets_text, file_names])
    response.then(lambda: gr.update(interactive=True), None, [msg], queue=False)


if __name__ == "__main__":
    demo.queue()
    demo.launch()
