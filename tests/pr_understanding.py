from math import log
from collections import Counter, defaultdict
import os
from git import Commit
from loguru import logger
import networkx as nx

from sweepai.config.client import SweepConfig
from sweepai.core.repo_parsing_utils import filter_file
from sweepai.utils.github_utils import ClonedRepo, get_github_client, get_installation_id

def build_file_graph(cloned_repo: ClonedRepo, k=400, sweep_config: SweepConfig = None):
    G = nx.Graph()
    all_files = []
    total_commits = 0
    file_count = Counter()
    for idx, commit in enumerate(cloned_repo.git_repo.iter_commits()):
        if idx == k:
            break
        def get_files(commit: Commit):
            files = [file for file in commit.stats.files.keys() if commit.stats.files[file]["lines"] > 10]
            return [file for file in files if filter_file(f"{cloned_repo.repo_dir}/", f"{cloned_repo.repo_dir}/{file}", sweep_config)]
        files = get_files(commit)
        logger.info(f"Commit message: {commit.message.strip()}")
        logger.info(f"Adding files from commit {files}")
        if len(files) < 2:
            continue
        for file in files:
            G.add_node(file)
            file_count[file] += 1
        all_files.append(files)
        total_commits += 1

    for files in all_files:
        for i in range(len(files)):
            for j in range(i+1, len(files)):
                # we weigh changes using tf-idf
                tf = 0.5 + (0.5 / len(files))
                # the more common a file is, the less weight it should have
                idf = log(total_commits / (file_count[files[i]] + file_count[files[j]] + 1))
                weight = tf * idf
                if G.has_edge(files[i], files[j]):
                    G[files[i]][files[j]]['weight'] += weight
                else:
                    G.add_edge(files[i], files[j], weight=weight)
    return G

if __name__ == "__main__":
    REPO_FULL_NAME = os.environ.get("REPO_FULL_NAME")
    sweep_config = SweepConfig()
    installation_id = get_installation_id(REPO_FULL_NAME.split("/")[0])

    _, g = get_github_client(installation_id)

    repo = g.get_repo(REPO_FULL_NAME)
    cloned_repo = ClonedRepo(REPO_FULL_NAME, installation_id, "main")

    file_graph = build_file_graph(cloned_repo, k=1000, sweep_config=sweep_config)
    # Perform community detection using the Louvain method
    communities = nx.community.louvain_communities(file_graph, weight='weight', resolution=2.0)

    # Calculate the percentage of nodes in each community
    total_nodes = file_graph.number_of_nodes()
    community_percentages = defaultdict(float)

    for community in communities:
        community_size = len(community)
        percentage = (community_size / total_nodes) * 100
        community_percentages[tuple(community)] = percentage

    # Print the percentage of nodes in each community
    for community, percentage in community_percentages.items():
        print(f"Community: {community}")
        print(f"Percentage of nodes: {percentage:.2f}%")
        print()
    breakpoint()

    # # Create a larger figure
    # fig, ax = plt.subplots(figsize=(30, 24))

    # # Visualize the graph with smaller text
    # pos = nx.spring_layout(file_graph)
    # nx.draw(file_graph, pos, with_labels=True, node_size=200, node_color='lightblue', font_size=4, edge_color='gray', ax=ax)
    # ax.set_title("File Graph", fontsize=16)
    # ax.axis('off')

    # # Save the plot to a file
    # output_path = "file_graph_large.png"
    # plt.savefig(output_path, dpi=300, bbox_inches='tight')
    # print(f"Plot saved to: {output_path}")