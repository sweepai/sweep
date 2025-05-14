from sweepai.core.chat import call_llm
from sweepai.logn.cache import file_cache
from sweepai.utils.github_utils import MockClonedRepo

instructions = "Explain in great detail what types of content this directory contains (code, documentation, configs, assets, tests etc.). Explain the purpose of the directory. Be concise and optimize for informational density. One paragraph."

system_prompt = "Your job is to summarize the following file from the repository. " + instructions

user_prompt = """Summarize the following file from the repository.

<repo_name>
{repo_name}
</repo_name>

<file_path>
{file_path}
</file_path>

<file_contents>
{file_contents}
</file_contents>

""" + instructions

@file_cache()
def summarize_file(file_path: str, file_contents: str, repo_name: str):
    response = call_llm(
        system_prompt,
        user_prompt,
        params={
            "repo_name": repo_name,
            "file_path": file_path,
            "file_contents": file_contents,
        },
        # verbose=False
    )

    return response

if __name__ == "__main__":
    cloned_repo = MockClonedRepo("/tmp/sweep", "sweepai/sweep")
    summarize_file("sweepai/handlers/on_ticket.py", cloned_repo)
