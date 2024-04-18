import numpy as np
from sweepai.core.vector_db import multi_get_query_texts_similarity
from sweepai.logn.cache import file_cache
from sweepai.utils.cohere_utils import cohere_rerank_call

from dataclasses import field, dataclass
from tqdm import tqdm

NUM_COMMITS = 10000

@dataclass
class Commit:
    sha: str
    message: str
    diff: str = field(repr=False)

@file_cache()
def get_previous_diffs(query, cloned_repo, relevant_file_paths: list[str]) -> str:
    # only get git blames of the file
    last_commits = []
    viewed_commits = set()
    for file_path in relevant_file_paths:
        for line in tqdm(cloned_repo.git_repo.git.blame("HEAD", "--", file_path).splitlines()):
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

    result_str = "<previous_diffs>\n{previous_diffs}\n</previous_diffs>\n"
    previous_diffs = ""
    for document in response.results[:5]:
        index = embed_index_to_rerank_index[document.index]
        previous_diffs += f"<previous_diff description={last_commits[index].message.strip()}>\n\n{last_commits[index].diff}\n</previous_diff>\n\n"
    result_str = result_str.format(previous_diffs=previous_diffs)
    return result_str if previous_diffs else ""