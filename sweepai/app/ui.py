import json
import os
import shutil
import tempfile
import re

import gradio as gr
from git import Repo
from github import Github
from loguru import logger

from sweepai.app.api_client import APIClient, create_pr_function, create_pr_function_call
from sweepai.app.config import State, SweepChatConfig
from sweepai.core.entities import Snippet
from sweepai.utils.config.client import SweepConfig

config = SweepChatConfig.load()

api_client = APIClient(config=config)

pr_summary_template = '''⏳ I'm creating the following PR...

**{title}**
{summary}

Here is my plan:
{plan}

Reply to propose changes to the plan.'''

print("Getting list of repos...")
github_client = Github(config.github_pat)
repos = list(github_client.get_user().get_repos())
print("Done.")

css = '''
footer {
    visibility: hidden;
}
pre, code {
    white-space: pre-wrap !important;
    word-break: break-all !important;
}
#snippets {
    height: 400px;
    overflow-y: scroll;
}
#message_box > label > span {
    display: none;
}
'''


def get_files_recursively(root_path, path=''):
    files = []
    path_to_contents = {}

    if path == '.git':
        return files, path_to_contents

    current_dir = os.path.join(root_path, path)
    entries = os.listdir(current_dir)

    for entry in entries:
        entry_path = os.path.join(current_dir, entry)

        if os.path.isfile(entry_path):
            try:
                with open(entry_path, 'r', encoding="utf-8", errors="ignore") as file:
                    contents = file.read()
                path_to_contents[entry_path[len(root_path) + 1:]] = contents
                files.append(entry_path[len(root_path) + 1:])
            except UnicodeDecodeError as e:
                logger.warning(f"Received warning {e}, skipping...")
                continue
        elif os.path.isdir(entry_path):
            subfiles, subpath_to_contents = get_files_recursively(root_path, os.path.join(path, entry))
            files.extend(subfiles)
            path_to_contents.update(subpath_to_contents)

    return files, path_to_contents


def get_installation_id(repo_full_name):
    config.repo_full_name = repo_full_name
    api_client.config = config
    installation_id = api_client.get_installation_id()
    return installation_id


path_to_contents = {}


def get_files(repo_full_name):
    global path_to_contents
    global repo
    if repo_full_name is None:
        all_files = []
    else:
        # Make sure repo is added to Sweep before checking all recursive files
        try:
            installation_id = get_installation_id(repo_full_name)
            assert installation_id
        except:
            return []
        repo = github_client.get_repo(repo_full_name)
        branch_name = SweepConfig.get_branch(repo)
        repo_url = f"https://x-access-token:{config.github_pat}@github.com/{repo_full_name}.git"
        try:
            repo_dir = os.path.join(tempfile.gettempdir(), repo_full_name)
            if os.path.exists(repo_dir):
                git_repo = Repo(repo_dir)
            else:
                git_repo = Repo.clone_from(repo_url, repo_dir)
            git_repo.git.checkout(branch_name)
            git_repo.remotes.origin.pull()
        except Exception as e:
            logger.warning(f"Git pull failed with error {e}, deleting cache and recloning...")
            shutil.rmtree(repo_dir)
            git_repo = Repo.clone_from(repo_url, repo_dir)
            git_repo.git.checkout(branch_name)
            git_repo.remotes.origin.pull()
        all_files, path_to_contents = get_files_recursively(repo_dir)
    return all_files


def get_files_update(*args):
    global repo
    if len(args) > 0:
        repo = args[0]
    else:
        repo = config.repo_full_name
    return gr.Dropdown.update(choices=get_files(repo))


def parse_response(raw_response: str) -> tuple[str, list[tuple[str, str]]]:
    if "Plan:" not in raw_response:
        response, raw_plan = raw_response, ""
    else:
        response, raw_plan = raw_response.split("Plan:", 1)
    if response.startswith("Response:"):
        response = response[len("Response:"):]
    plan = [(line[:line.find(":")].strip(), line[line.find(":") + 1:].strip()) for line in raw_plan.split("\n*") if
            line]
    return response, plan


global_state = config.state

with gr.Blocks(theme=gr.themes.Soft(), title="Sweep Chat", css=css) as demo:
    print("Launching gradio!")
    with gr.Row():
        with gr.Column(scale=2):
            repo_full_name = gr.Dropdown(choices=[repo.full_name for repo in repos], label="Repo full name",
                                         value=lambda: config.repo_full_name or "")
        print("Indexing files...")
        with gr.Column(scale=4):
            file_names = gr.Dropdown(choices=get_files(config.repo_full_name), multiselect=True, label="Files",
                                     value=lambda: global_state.file_paths)
        print("Indexed files!")
        repo_full_name.change(get_files_update, repo_full_name, file_names)
        with gr.Column(scale=1):
            restart_button = gr.Button("Restart")

    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=400, value=lambda: global_state.chat_history)
        with gr.Column():
            with gr.Row():
                snippets_text = gr.Markdown(value=lambda: global_state.snippets_text, elem_id="snippets")

    with gr.Row():
        plan = gr.List(
            value=[[filename + ": " + instructions] for filename, instructions in global_state.plan],
            headers=["Proposed Plan"],
            interactive=True,
            col_count=(1, "static"),
            wrap=True
        )

    with gr.Row():
        with gr.Column(scale=8):
            msg = gr.Textbox(placeholder="Send a message to Sweep", label=None, elem_id="message_box")
        with gr.Column(scale=0.5):
            create_pr_button = gr.Button(value="Create PR", interactive=bool(global_state.chat_history))


    def clear_inputs():
        global global_state
        global_state = State()
        config.state = global_state
        config.save()
        return [], [], [[""]]


    restart_button.click(clear_inputs, None, [file_names, chatbot, plan])

    file_names.change(get_files_update, repo_full_name, chatbot)

    searched = False
    selected_snippets = []
    file_to_str = {}


    def repo_name_change(repo_full_name):
        global installation_id
        try:
            installation_id = get_installation_id(repo_full_name)
            assert installation_id
            config.installation_id = installation_id
            api_client.config = config
            config.save()
            return ""
        except Exception as e:
            config.repo_full_name = None
            config.installation_id = None
            config.save()
            api_client.config = config
            raise e


    def build_string():
        global selected_snippets
        global file_to_str
        for snippet in selected_snippets:
            file_name = snippet.file_path
            if file_name not in file_to_str:
                add_file_to_dict(file_name)
        snippets_text = "### Relevant snippets:\n" + "\n\n".join(
            [file_to_str[snippet.file_path] for snippet in selected_snippets])
        return snippets_text


    repo_full_name.change(repo_name_change, [repo_full_name], [msg])


    def add_file_to_dict(file_name):
        global file_to_str
        global path_to_contents
        global repo
        if file_name in path_to_contents:
            file_contents = path_to_contents[file_name]
        else:
            file_contents = repo.get_contents(file_name, ref=SweepConfig.get_branch(repo)).decoded_content.decode(
                'utf-8')
        file_contents_split = file_contents.split("\n")
        length = len(file_contents_split)
        backtick, escaped_backtick = "`", "\\`"
        preview = "\n".join(file_contents_split[:3]).replace(backtick, escaped_backtick)
        file_to_str[file_name] = f'{file_name}:0:{length}\n```\n{preview}\n...\n```'


    def file_names_change(file_names):
        global selected_snippets
        global file_to_str
        global path_to_contents
        selected_snippets = [
            Snippet(content=path_to_contents[file_name], start=0, end=path_to_contents[file_name].count('\n'),
                    file_path=file_name) for file_name in file_names]
        return file_names, build_string()


    file_names.change(file_names_change, [file_names], [file_names, snippets_text])


    def handle_message_submit(repo_full_name: str, user_message: str, history: list[tuple[str | None, str | None]]):
        if not repo_full_name:
            raise Exception("Set the repository name first")
        return gr.update(value="", interactive=False), history + [[user_message, None]], gr.Button.update(
            interactive=True)


    def _handle_message_stream(chat_history: list[tuple[str | None, str | None]], snippets_text, file_names, plan):
        global selected_snippets
        global searched
        if plan is None or plan == [[]] or plan == [[""]] or plan == [["", ""]]:
            plan = [["", ""]]
        message = chat_history[-1][0]
        yield chat_history, snippets_text, file_names, plan
        if not selected_snippets:
            searched = True
            # Searching for relevant snippets
            chat_history[-1][1] = "Searching for relevant snippets..."
            snippets_text = build_string()
            yield chat_history, snippets_text, file_names, plan
            logger.info("Fetching relevant snippets...")
            selected_snippets += api_client.search(chat_history[-1][0], 3)
            snippets_text = build_string()
            file_names = [snippet.file_path for snippet in selected_snippets]
            yield chat_history, snippets_text, file_names, plan
            logger.info("Fetched relevant snippets.")
            chat_history[-1][1] = "Found relevant snippets."
            # Update using chat_history
            snippets_text = build_string()
            yield chat_history, snippets_text, file_names, plan

        # Generate response
        logger.info("...")
        chat_history.append([None, "..."])
        yield chat_history, snippets_text, file_names, plan
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
        raw_response = ""
        parsed_response = ""
        for chunk in stream:
            if chunk.get("content"):
                token = chunk["content"]
                raw_response += token
                parsed_response, plan = parse_response(raw_response)
                chat_history[-1][1] = parsed_response
                yield chat_history, snippets_text, file_names, plan
            if chunk.get("function_call"):
                function_call = chunk["function_call"]
                function_name = function_name or function_call.get("name")
                raw_arguments += function_call.get("arguments")
                chat_history[-1][1] = f"Calling function: `{function_name}`\n```json\n{raw_arguments}\n```"
                yield chat_history, snippets_text, file_names, plan
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
                yield chat_history, snippets_text, file_names, plan
                plan = [(item["file_path"], item["instructions"]) for item in arguments["plan"]]
                yield chat_history, snippets_text, file_names, plan
            else:
                raise NotImplementedError


    def handle_message_stream(chat_history: list[tuple[str | None, str | None]], snippets_text, file_paths, plan):
        global global_state
        for chat_history, snippets_text, file_paths, plan in _handle_message_stream(chat_history, snippets_text,
                                                                                    file_paths, plan):
            if plan is None or plan == [[]] or plan == [[""]] or plan == [["", ""]]:
                plan = [["", ""]]
            if plan and isinstance(plan[0], list):
                plan = [item.split(":") for item in plan]
            global_state = State(
                chat_history=chat_history,
                snippets_text=snippets_text,
                file_paths=file_paths,
                plan=plan,
            )
            config.state = global_state
            config.save()
            yield chat_history, snippets_text, file_paths, [(file_path + ": " + instructions,) for
                                                            file_path, instructions in plan]


    response = msg \
        .submit(handle_message_submit, [repo_full_name, msg, chatbot], [msg, chatbot, create_pr_button], queue=False) \
        .then(handle_message_stream, [chatbot, snippets_text, file_names, plan],
              [chatbot, snippets_text, file_names, plan]) \
        .then(lambda: gr.update(interactive=True), None, [msg], queue=False)


    def validate_branch_name(branch_name):
        # Replace any characters that are not alphanumeric or '-' or '_' with '_'
        valid_branch_name = re.sub('[^0-9a-zA-Z_-]', '_', branch_name)
        return valid_branch_name

    def on_create_pr_button_click(chat_history: list[tuple[str | None, str | None]], plan: list[tuple[str]]):
        chat_history.append((None, "⌛ Creating PR..."))
        yield chat_history
        title = chat_history[0][0]
        content = chat_history[-1][1]
        # Validate the branch name before it's used in the create_pr function
        valid_branch_name = validate_branch_name(title.lower().replace(" ", "_").replace("-", "_")[:50])
        pull_request = api_client.create_pr(
            file_change_requests=[(item[:item.find(":")], item[item.find(":") + 1:]) for item, *_ in plan],
            pull_request={
                "title": title,
                "content": content,
                "branch_name": valid_branch_name
            },
            messages=chat_history,
        )
        chat_history.append((None, f"✅ PR created at {pull_request['html_url']}"))
        yield chat_history


    create_pr_button.click(on_create_pr_button_click, [chatbot, plan], chatbot)

if __name__ == "__main__":
    demo.queue()
    demo.launch()
