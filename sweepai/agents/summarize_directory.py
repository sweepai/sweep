import os

from loguru import logger

from sweepai.core.entities import SNIPPET_FORMAT
from sweepai.config.client import SweepConfig
from sweepai.core.chat import call_llm
from sweepai.core.entities import Snippet
from sweepai.logn.cache import file_cache
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.timer import Timer

FILE_THRESHOLD = 240

@file_cache() # cache for now, later investigate why this is so slow
def count_descendants(directory: str):
    descendant_count = {}
    dir_file_count = {}

    def is_dir_too_big(file_name):
        dir_name = os.path.dirname(file_name)
        file_sections = file_name.split(os.sep)
        for name in ("node_modules", ".venv", "build", "venv", "patch"):
            if name in file_sections:
                return True
        if dir_name not in dir_file_count:
            dir_file_count[dir_name] = len(os.listdir(dir_name))
        return dir_file_count[dir_name] > FILE_THRESHOLD

    def dfs(current_dir):
        count = 0
        for root, dirs, files in os.walk(current_dir):
            if is_dir_too_big(root):
                continue
            for d in dirs:
                if is_dir_too_big(os.path.join(root, d)):
                    continue
                count += dfs(os.path.join(root, d))
            count += len(files)
        descendant_count[current_dir.removeprefix(directory.rstrip() + "/")] = count
        return count

    print("Counting descendants")
    with Timer():
        dfs(directory)
    print("Done counting descendants")
    for key in (".git", "", directory):
        if key in descendant_count:
            del descendant_count[key]
    return descendant_count


instructions = "Do NOT list the files, just explain what types of content this directory contains (code, documentation, configs, assets, tests etc.). Explain the purpose of the directory. Only list describe contents that appear in multiple files.  Be concise and optimize for informational density. One paragraph."

system_prompt = "Your job is to summarize the following directory from the repository. " + instructions

user_prompt = """Summarize the following directory from the repository.

Repository:
{repo_name}

Directory:
{directory}

<example_files>
{snippets_string}
</example_files>

""" + instructions

def summarize_directory(
    directory: str,
    snippets: list[Snippet],
    cloned_repo: ClonedRepo,
    directory_summaries: dict[str, str] = {},
):
    snippets_string = "\n\n".join([SNIPPET_FORMAT.format(
        denotation=snippet.denotation,
        contents=snippet.expand(50).get_snippet(False, False)
    ) for snippet in snippets])

    for subdir, summary in directory_summaries.items():
        if subdir.startswith(directory) and summary:
            snippets_string += f"\n\nHere is a summary of the subdirectory {subdir}:\n\n" + summary
            # breakpoint()

    response = call_llm(
        system_prompt,
        user_prompt,
        params={
            "repo_name": cloned_repo.repo_full_name,
            "directory": directory,
            "snippets_string": snippets_string.strip(),
        },
        verbose=False
    )

    return response

NUM_SNIPPET_EXAMPLES = 10

def recursively_summarize_directory(
    snippets: list[Snippet],
    cloned_repo: ClonedRepo,
):
    directory = cloned_repo.repo_dir
    descendant_counts = count_descendants(directory)
    directory_summaries = {}
    # go in reverse order

    for subdir in sorted(descendant_counts, key=lambda x: descendant_counts[x]):
        if descendant_counts[subdir] <= 5:
            continue
        logger.info(f"Summarizing {subdir}")
        snippets_in_subdir = [snippet for snippet in snippets if snippet.file_path.removeprefix(cloned_repo.repo_dir).removeprefix("/").startswith(subdir)][:NUM_SNIPPET_EXAMPLES]
        if not snippets_in_subdir:
            continue
        directory_summaries[subdir] = summarize_directory(
            subdir,
            snippets_in_subdir,
            cloned_repo,
            directory_summaries
        )
    for subdir, summary in directory_summaries.items():
        print(subdir)
        print(summary)
        print("\n")
    return directory_summaries


if __name__ == "__main__":
    from sweepai.utils.github_utils import MockClonedRepo
    from sweepai.core.lexical_search import prepare_lexical_search_index
    cloned_repo = MockClonedRepo("/tmp/sweep", "sweepai/sweep")
    directory = "docs"
    directory = "sweepai/core"
    directory = "sweepai/agents"

    snippets, lexical_index = prepare_lexical_search_index(
        cloned_repo.repo_dir,
        SweepConfig(),
    )

    print(
        recursively_summarize_directory(
            snippets,
            cloned_repo,
        )
    )
