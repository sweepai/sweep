import re
import numpy as np
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.vector_db import multi_get_query_texts_similarity
# from sweepai.logn.cache import file_cache
from sweepai.utils.cohere_utils import cohere_rerank_call

from dataclasses import field, dataclass
from tqdm import tqdm

from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo

NUM_COMMITS = 10000

generate_query_instructions = """Objective: Assist an engineer in resolving a GitHub issue by crafting a precise natural language search query. This query will be used in a vector search engine to find solutions from similar past issues.
Steps:
- Identify the existing feature in the codebase that most closely resembles the current issue.
    - Example: If the current issue involves adding a filter to hide deleted posts, a similar feature might be adding a filter to hide deleted users.
- Compose a high-quality search query designed to locate the commit that implemented the identified similar feature.
- The search query should be specific and targeted, using relevant keywords and phrases to narrow down the search results effectively.
- Provide an analysis that outlines the reasoning behind the selected similar feature and the thought process used to create the search query.
- Present the final search query within XML blocks to ensure it is clearly distinguishable and easy to extract.

Format:
<analysis>
The COT block should include:
An explanation of why the identified feature is considered the most similar to the current issue.
A breakdown of the key components and considerations used to construct the search query.
Any assumptions made or additional information that could help refine the search query.
</analysis>

Final Search Query:
<query>
Insert the final natural language search query here, ensuring it is specific, targeted, and includes relevant keywords and phrases to effectively narrow down the search results. It should be a command starting with "Find the commit that...". Do NOT reference any files.
</query>

Note: The example provided below is for illustration purposes only. When using this prompt, focus on the actual input issue and codebase to identify the most relevant similar feature and craft an appropriate search query.

Example:

Current Issue: Implement a feature to allow users to mark comments as spoilers, hiding the content until clicked.

Chain of Thought (COT):
<cot>
The most similar existing feature to marking comments as spoilers is the implementation of the "Show/Hide" functionality for sensitive content in posts. This feature allows users to hide sensitive content behind a warning message, requiring a click to reveal the hidden content.

To search for the commit that implemented this feature, the query should reference specific entities such as the "Post" and "Content" models, as well as relevant actions like "hide," "show," "click," and "reveal." Additionally, mentioning the "warning message" and the "sensitive" nature of the content can help pinpoint the desired commit more accurately.
</cot>

Final Search Query:
<query>
Find the commit that introduced the functionality to hide sensitive content within a Post entity behind a warning message, allowing users to click and reveal the hidden Post.Content, similar to a "spoiler" feature for comments.
</query>"""

generate_query_user_prompt = """<relevant_files>
{relevant_files}
</relevant_files>

<github_issue>
{github_issue}
</github_issue>

""" + generate_query_instructions

commit_selection_format_prompt = """Respond in the following format. First think step-by-step, then select any commits to show to the engineer. You don't want to overload the engineer with noise so only pick commits containing code that would be very similar to the final implementation.

<thinking>
Summarize each commit and the issue and think step-by-step. Then determine which commits contain code that would be very similar to the final implementation for this current feature, as well as which files from each commit contains relevant information. Avoid adding files with large diffs that are not relevant to the current feature.
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

def generate_query(query: str, cloned_repo: ClonedRepo, relevant_file_path: list[str]) -> str:
    chatgpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=generate_query_instructions
            ),
        ]
    )
    relevant_files_string = ""
    file_contents = []
    for file_path in relevant_file_path:
        try:
            file_contents = cloned_repo.get_file_contents(file_path)
        except FileNotFoundError:
            continue
        relevant_files_string += f"<relevant_file>\n<file_path>\n{file_path}\n</file_path>\n<source>\n{file_contents}\n</source>\n</relevant_file>"
    relevant_files_string = f"<relevant_files>\n{relevant_files_string}\n</relevant_files>"
    user_message = generate_query_user_prompt.format(
        relevant_files=relevant_files_string,
        github_issue=query
    )
    response = chatgpt.chat_anthropic(
        user_message,
        model="claude-3-opus-20240229", # Sonnet doesn't work well with this prompt
    )
    match_ = re.search(r"<query>(.*?)</query>", response, re.DOTALL)
    if match_:
        return match_.group(1).strip()
    else:
        return query

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

    enhanced_query = generate_query(query, cloned_repo, relevant_file_paths)
    similarities = np.array(multi_get_query_texts_similarity([enhanced_query], [last_commit.message + last_commit.diff for last_commit in last_commits]))
    top_indices = [index for index in similarities.flatten().argsort()[-1000:][::-1]]
    top_documents = [last_commits[index].message + last_commits[index].diff for index in top_indices]
    embed_index_to_rerank_index = {rank_index: actual_index for rank_index, actual_index in enumerate(top_indices)}

    NUM_DIFFS = 5
    try:
        response = cohere_rerank_call(enhanced_query, top_documents)
        commits = []
        for document in response.results[:NUM_DIFFS]:
            index = embed_index_to_rerank_index[document.index]
            commit = last_commits[index]
            commits.append(commit)
    except Exception as e:
        print(e)
        commits = [last_commits[index] for index in top_indices[:NUM_DIFFS]]

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
        model="claude-3-opus-20240229", # Sonnet fails at this task
    )
    commits_pattern = re.compile(r"<commit>\s*?<sha>(?P<sha>.*?)</sha>\s*?<file_paths>\s*?(?P<file_paths>.*?)\s*?</file_paths>\s*?</commit>", re.DOTALL)
    result_str = ""
    for match in commits_pattern.finditer(response):
        commit_sha = match.group("sha").strip()
        commit = next(commit for commit in commits if commit.sha == commit_sha)
        file_paths = match.group("file_paths").strip().splitlines()
        diff_mapping = get_diff_mapping(commit.diff)
        filtered_diffs = "\n".join([diff_mapping[file_path] for file_path in file_paths if file_path in diff_mapping])
        result_str += f"<commit>\n<sha>{commit_sha}</sha>\n<commit_message>\n{commit.message}\n</commit_message>\n<source>\n{filtered_diffs}\n</source>\n</commit>\n"
    result_str = f"<relevant_existing_commits>\n{result_str.strip()}\n</relevant_existing_commits>"
    return result_str

if __name__ == "__main__":
    from sweepai.utils.github_utils import MockClonedRepo

    query = """Where is the code that handles the API?"""
    directory = "/mnt/sweep_benchmark/sweep"
    relevant_file_paths = ["sweepai/api.py"]
    cloned_repo = MockClonedRepo(
        _repo_dir=directory,
        repo_full_name="sweepai/sweep"
    )
    print(get_relevant_commits(query, cloned_repo, relevant_file_paths))
