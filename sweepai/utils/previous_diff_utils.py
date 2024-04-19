import re
import numpy as np
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.vector_db import multi_get_query_texts_similarity
from sweepai.logn.cache import file_cache
from sweepai.utils.cohere_utils import cohere_rerank_call

from dataclasses import field, dataclass
from tqdm import tqdm

from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo

NUM_COMMITS = 10000

commit_selection_format_prompt = """Respond in the following format. First think step-by-step, then select any commits to show to the engineer. You don't want to overload the engineer with noise so only pick commits containing code that would be very similar to the final implementation.

<thinking>
Summarize each commit and the issue and think step-by-step. Then determine which commits contain code that would be very similar to the final implementation for this current feature, as well as which files from each commit contains relevant information
</thinking>

<selected_commits>
<commit>
<sha>The commit sha.</sha>
<file_paths>
File paths, one per line, that contain relevant diffs.
</file_paths>
[additional file paths with relevant diffs]
</commit>
[additional commits, if any]
</selected_commits>"""

commit_selection_system_prompt = """Your job is to help an engineer solve a GitHub issue by finding past solutions to similar issues. For example, if the current issue is that the app is showing deleted posts and previously a developer fixed a bug relating to the app showing deleted users, the implementations would be very similar and therefore this can be helpful.

You will list any previous commits that could be a potential reference implementation to the feature requested by the user.

""" + commit_selection_format_prompt

commit_selection_user_prompt = """<github_issue>
{github_issue}
</github_issue>

<similar_commits>
{similar_commits}
</similar_commits>

""" + commit_selection_format_prompt

def get_diff_mapping(patch: str) -> dict[str, str]: 
    """
    Returns file path to diff hunk mapping
    """
    diff_mapping = {}
    for hunk in patch.split("diff --git "):
        if not hunk.strip():
            continue
        file_path = hunk.split(" b/")[0].removeprefix("a/")
        diff_mapping[file_path] = "diff --git " + hunk
    return diff_mapping

@dataclass
class Commit:
    sha: str
    message: str
    diff: str = field(repr=False)

    @property
    def xml(self):
        return f"<commit>\n<commit_sha>{self.sha}</commit_sha>\n<commit_message>\n{self.message}\n</commit_message>\n<source>\n{self.diff}\n</source>\n</commit>"

def generate_query(query: str) -> str:
    return query

@file_cache()
def query_relevant_commits(query: str, cloned_repo: ClonedRepo, relevant_file_paths: list[str]) -> list[Commit]:
    # only get git blames of the file
    last_commits = []
    viewed_commits = set()
    all_lines = []
    for file_path in relevant_file_paths:
        all_lines.extend(cloned_repo.git_repo.git.blame("HEAD", "--", file_path).splitlines())

    for line in tqdm(all_lines):
        if not line:
            continue
        sha, _message = line.split(" ", 1)
        if sha in viewed_commits:
            continue
        viewed_commits.add(sha)
        diff = cloned_repo.git_repo.git.diff(f"{sha}~1", sha)
        full_message = cloned_repo.git_repo.git.show("--no-indent", "--no-patch", "--format=%s%n%n%b", sha)
        last_commits.append(Commit(sha=sha, message=full_message, diff=diff))

    similarities = np.array(multi_get_query_texts_similarity([query], [last_commit.message + last_commit.diff for last_commit in last_commits]))
    top_indices = [index for index in similarities.flatten().argsort()[-1000:][::-1]]
    top_documents = [last_commits[index].message + last_commits[index].diff for index in top_indices]
    embed_index_to_rerank_index = {rank_index: actual_index for rank_index, actual_index in enumerate(top_indices)}

    response = cohere_rerank_call(query, top_documents)

    commits = []
    for document in response.results[:3]:
        index = embed_index_to_rerank_index[document.index]
        commit = last_commits[index]
        commits.append(commit)
    
    return commits

def get_relevant_commits(query: str, cloned_repo: ClonedRepo, relevant_file_paths: list[str]) -> list[Commit]:
    commits = query_relevant_commits(query, cloned_repo, relevant_file_paths)
    commits_str = "\n".join([commit.xml for commit in commits])
    user_prompt = commit_selection_user_prompt.format(github_issue=query, similar_commits=commits_str)
    chatgpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=commit_selection_system_prompt
            ),
        ]
    )
    response = chatgpt.chat_anthropic(
        user_prompt,
        model="claude-3-sonnet-20240229",
    )
    commits_pattern = re.compile(r"<commit>\s*?<sha>(?P<sha>.*?)</sha>\s*?<file_paths>\s*?(?P<file_paths>.*?)\s*?</file_paths>\s*?</commit>", re.DOTALL)
    result_str = ""
    for match in commits_pattern.finditer(response):
        commit_sha = match.group("sha").strip()
        commit = next(commit for commit in commits if commit.sha == commit_sha)
        file_paths = match.group("file_paths").strip().splitlines()
        diff_mapping = get_diff_mapping(commit.diff)
        filtered_diffs = "\n".join([diff_mapping[file_path] for file_path in file_paths])
        result_str += f"<commit>\n<sha>{commit_sha}</sha>\n<commit_message>\n{commit.message}\n</commit_message>\n<source>\n{filtered_diffs}\n</source>\n</commit>\n"
    result_str = f"<relevant_existing_commits>\n{result_str.strip()}\n</relevant_existing_commits>"
    breakpoint()
    return results_str

if __name__ == "__main__":
    from sweepai.utils.github_utils import MockClonedRepo

    query = """Django admin commit that introduced the ability to hide "Save" and "Save and continue editing" buttons on the change form by passing `show_save` and `show_save_and_continue` variables in the template context. This allowed controlling visibility of these save buttons based on context passed from the view."""
    directory = "/mnt/sweep_benchmark/django__django-11727"
    cloned_repo = MockClonedRepo(
        _repo_dir=directory,
        repo_full_name="django/django"
    )
    relevant_file_paths = ["django/contrib/admin/templatetags/admin_modify.py", "django/contrib/admin/options.py", "django/contrib/admin/templates/admin/submit_line.html", "django/contrib/admin/helpers.py"]
    print(get_relevant_commits(query, cloned_repo, relevant_file_paths))
