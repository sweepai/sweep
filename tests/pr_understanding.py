from math import log
from collections import Counter
import os
from loguru import logger
import networkx as nx
from networkx import Graph
from tqdm import tqdm

from sweepai.config.client import SweepConfig
from sweepai.core.repo_parsing_utils import filter_file
from sweepai.logn.cache import file_cache
from sweepai.utils.github_utils import ClonedRepo, get_github_client, get_installation_id

def build_file_graph(cloned_repo: ClonedRepo, k=400, sweep_config: SweepConfig = None):
    G = nx.Graph()
    all_files = []
    all_file_scores = []
    total_commits = 0
    file_count = Counter()

    git_commit_files = []
    for idx, commit in tqdm(enumerate(cloned_repo.git_repo.iter_commits())):
        if idx == k:
            break
        # remove merge commits - super noisy
        cleaned_message = "".join([i for i in commit.message.lower() if i.isalnum()])
        # if cleaned_message.startswith("merge"):
        #     logger.info(f"Skipping merge commit: {commit.message} with {len(commit.stats.files)} files")
        #     continue
        git_commit_files.append(commit.stats.files)

    for idx, commit_stats_files in tqdm(enumerate(git_commit_files)):

        files = [file for file in commit_stats_files.keys() if commit_stats_files[file]["insertions"] > 10 and filter_file(f"{cloned_repo.repo_dir}/", f"{cloned_repo.repo_dir}/{file}", sweep_config)]

        if len(files) < 2:
            continue

        file_scores = {file: commit_stats_files[file]["insertions"] for file in files}
        all_files.append(files)
        all_file_scores.append(file_scores)
        total_commits += 1
    
    # get the length of all files
    all_file_lengths = Counter()
    flattened_files = [file for files in all_files for file in files]
    for file in flattened_files:
        if file not in all_file_lengths:
            file_length = cloned_repo.get_file_contents(file).count("\n")
            all_file_lengths[file] = file_length
        G.add_node(file)
        file_count[file] += 1

    DAMPENING = 10
    for files, file_scores in zip(all_files, all_file_scores):
        for i in range(len(files)):
            for j in range(i+1, len(files)):
                # there's always at least 2 files
                tf = 0.5 + (0.5 / len(files))
                # the more common a file is, the less weight it should have
                idf = log(total_commits / (file_count[files[i]] + DAMPENING) * log(total_commits / file_count[files[j]] + DAMPENING))
                # if the insertions are greater than the current length of the file, we should cap the score at 0.2
                # added log multiplier to give more weight to longer files, might need to rework
                file_score_i = min(file_scores[files[i]] / all_file_lengths[files[i]], 0.2) * log(all_file_lengths[files[i]])
                file_score_j = min(file_scores[files[j]] / all_file_lengths[files[j]], 0.2) * log(all_file_lengths[files[j]])
                weight = tf * idf * file_score_i * file_score_j
                logger.info(f"Adding edge between {files[i]} and {files[j]} with weight {weight}, tf: {tf}, idf: {idf}, file_score_i: {file_score_i}, file_score_j: {file_score_j}")
                if G.has_edge(files[i], files[j]):
                    G[files[i]][files[j]]['weight'] += weight
                else:
                    G.add_edge(files[i], files[j], weight=weight)
    return G

def get_relevant_neighbors(G: Graph, candidate_node, top_k=10):
    sorted_neighbors = sorted([i for i in dict(file_graph[candidate_file]).items()], key=lambda x: x[1]['weight'], reverse=True)
    files_and_scores = [(file, data['weight']) for file, data in sorted_neighbors]
    for file, weight in files_and_scores[:top_k]:
        print(f"File: {file}, Weight: {weight}")
    return files_and_scores[:top_k]

if __name__ == "__main__":
    REPO_FULL_NAME = os.environ.get("REPO_FULL_NAME")
    sweep_config = SweepConfig()
    installation_id = get_installation_id(REPO_FULL_NAME.split("/")[0])

    _, g = get_github_client(installation_id)

    repo = g.get_repo(REPO_FULL_NAME)
    
    @file_cache()
    def get_graph(repo_name=REPO_FULL_NAME) -> Graph:
        default_branch = repo.default_branch
        cloned_repo = ClonedRepo(REPO_FULL_NAME, installation_id, default_branch)
        file_graph = build_file_graph(cloned_repo, k=1000, sweep_config=sweep_config)
        return file_graph
    file_graph = get_graph(repo_name=REPO_FULL_NAME)
    candidate_file = "sweepai/chat/api.py"
    top_relevant_files = get_relevant_neighbors(file_graph, candidate_file, top_k=30)
    print("\n\n")