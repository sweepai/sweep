

from loguru import logger
from github.Repository import Repository
from sweepai.config.client import RESET_FILE
from sweepai.core.sweep_bot import SweepBot
from sweepai.utils.buttons import ButtonList
from sweepai.utils.github_utils import get_github_client


def handle_button_click(request_dict):
    _, g = get_github_client(request_dict["installation"]["id"])
    button_list = ButtonList.deserialize(request_dict["comment"]["body"])
    selected_buttons = [button.label for button in button_list.get_clicked_buttons()]
    revert_files = []
    for button_text in selected_buttons:
        revert_files.append(button_text.split(f"{RESET_FILE} ")[-1].strip())
    repo = g.get_repo(request_dict["repository"]["full_name"]) # do this after checking ref
    handle_revert(revert_files, request_dict["issue"]["number"], repo)

def handle_revert(file_paths, pr_number, repo: Repository):
    pr = repo.get_pull(pr_number)
    branch_name = pr.head.ref if pr_number else pr.pr_head
    def get_contents_with_fallback(repo: Repository, file_path: str, branch: str = None):
        try:
            if branch: return repo.get_contents(file_path, ref=branch)
            return repo.get_contents(file_path)
        except Exception as e:
            return None
    old_file_contents = [ get_contents_with_fallback(repo, file_path) for file_path in file_paths]
    for file_path, old_file_content in zip(file_paths, old_file_contents):
        try:
            current_content = repo.get_contents(file_path, ref=branch_name)
            if old_file_content:
                repo.update_file(
                    file_path,
                    f"Revert {file_path}",
                    old_file_content.decoded_content,
                    sha=current_content.sha,
                    branch=branch_name,
                )
            else:
                repo.delete_file(
                    file_path,
                    f"Delete {file_path}",
                    sha=current_content.sha,
                    branch=branch_name,
                )
        except Exception as e:
            pass # file may not exist and this is expected