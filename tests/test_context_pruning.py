import unittest
from sweepai.core.context_pruning import (
    build_full_hierarchy,
    load_graph_from_file,
    RepoContextManager,
    get_relevant_context,
)
import networkx as nx

class TestContextPruning(unittest.TestCase):
    def test_build_full_hierarchy(self):
        G = nx.DiGraph()
        G.add_edge("main.py", "database.py")
        G.add_edge("database.py", "models.py")
        G.add_edge("utils.py", "models.py")
        hierarchy = build_full_hierarchy(G, "main.py", 2)
        expected_hierarchy = """main.py
├── database.py
│   └── models.py
└── utils.py
    └── models.py
"""
        self.assertEqual(hierarchy, expected_hierarchy)

    def test_load_graph_from_file(self):
        graph = load_graph_from_file("tests/test_import_tree.txt")
        self.assertIsInstance(graph, nx.DiGraph)
        self.assertEqual(len(graph.nodes), 5)
        self.assertEqual(len(graph.edges), 4)

    def test_get_relevant_context(self):
        cloned_repo = ClonedRepo("sweepai/sweep", "123", "main")
        repo_context_manager = RepoContextManager(
            dir_obj=None,
            current_top_tree="",
            snippets=[],
            snippet_scores={},
            cloned_repo=cloned_repo,
        )
        query = "allow 'sweep.yaml' to be read from the user/organization's .github repository. this is found in client.py and we need to change this to optionally read from .github/sweep.yaml if it exists there"
        rcm = get_relevant_context(
            query,
            repo_context_manager,
            seed=42,
            ticket_progress=None,
            chat_logger=None,
        )
        self.assertIsInstance(rcm, RepoContextManager)
        self.assertTrue(len(rcm.current_top_snippets) > 0)
        self.assertTrue(any("client.py" in snippet.file_path for snippet in rcm.current_top_snippets))