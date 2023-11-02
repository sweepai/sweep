import unittest
from unittest.mock import mock_open, patch

import networkx as nx

from sweepai.utils.graph import (
    Graph,
    condense_paths,
    draw_paths_on_graph,
    extract_degree_paths,
    extract_entities,
    format_path,
    traverse_folder,
    extract_degree_paths,
    condense_paths
)


class TestGraph(unittest.TestCase):
    def setUp(self):
        self.graph = Graph(
            definitions_graph=nx.DiGraph(), references_graph=nx.DiGraph()
        )

    def test_extract_first_degree(self):
        with patch(
            "sweepai.utils.graph.Graph.find_definitions"
        ) as mock_find_definitions, patch(
            "sweepai.utils.graph.Graph.find_references"
        ) as mock_find_references, patch(
            "sweepai.utils.graph.condense_paths"
        ) as mock_condense_paths:
            mock_find_definitions.return_value = [["file1", "symbol1", "file2"]]
    def test_file_encoding(self):
        with patch("builtins.open", new_callable=mock_open, read_data="test data") as mock_file:
            mock_file.return_value.__iter__.return_value = ["test data"]
            mock_file.return_value.encoding = "utf-8"
            result = extract_entities(mock_file.return_value.read())
            self.assertEqual(result, (["test"], [], []))

        with patch("builtins.open", new_callable=mock_open, read_data="test data") as mock_file:
            mock_file.return_value.__iter__.return_value = ["test data"]
            mock_file.return_value.encoding = "utf-16"
            result = extract_entities(mock_file.return_value.read())
            self.assertEqual(result, (["test"], [], []))

    def test_path_formatting(self):
        path = ["file1", "symbol1", "file2"]
        result = format_path(path)
        self.assertEqual(result, "symbol1 uses file2")

        path = ["file1", "symbol1", "file2", "symbol2", "file3"]
        result = format_path(path)
        self.assertEqual(result, "symbol1 uses file2 uses symbol2 uses file3")

    def test_extract_first_degree(self):
        with patch(
            "sweepai.utils.graph.Graph.find_definitions"
        ) as mock_find_definitions, patch(
            "sweepai.utils.graph.Graph.find_references"
        ) as mock_find_references, patch(
            "sweepai.utils.graph.condense_paths"
        ) as mock_condense_paths:
            mock_find_definitions.return_value = [["file1", "symbol1", "file2"]]
            mock_find_references.return_value = [["file1", "symbol1", "file2"]]
            mock_condense_paths.return_value = [["file1", "symbol1", "file2"]]
            with patch(
                "sweepai.utils.graph.Graph.topological_sort"
            ) as mock_topological_sort:
                mock_topological_sort.return_value = ["file1", "file2"]
                result = self.graph.topological_sort(["file1", "file2"])
                self.assertEqual(result, ["file1", "file2"])

    def test_find_definitions(self):
        with patch(
            "sweepai.utils.graph.extract_degree_paths"
        ) as mock_extract_degree_paths:
            mock_extract_degree_paths.return_value = [["file1", "symbol1", "file2"]]
            result = self.graph.find_definitions("file1")
            self.assertEqual(result, [["file1", "symbol1", "file2"]])

    def test_find_references(self):
        with patch(
            "sweepai.utils.graph.extract_degree_paths"
        ) as mock_extract_degree_paths:
            mock_extract_degree_paths.return_value = [["file1", "symbol1", "file2"]]
            result = self.graph.find_references("file1")
            self.assertEqual(result, [["file1", "symbol1", "file2"]])

    def test_paths_to_first_degree_entities(self):
        with patch(
            "sweepai.utils.graph.Graph.extract_first_degree"
        ) as mock_extract_first_degree:
            mock_extract_first_degree.return_value = (
                "file1 defined in symbol1\nfile1 used in symbol1\n"
            )
            with patch(
                "sweepai.utils.graph.Graph.paths_to_first_degree_entities"
            ) as mock_paths_to_first_degree_entities:
                mock_paths_to_first_degree_entities.return_value = "file1 defined in symbol1\nfile1 used in symbol1\nfile1 defined in symbol1\nfile1 used in symbol1\n"
                result = self.graph.paths_to_first_degree_entities(["file1", "file2"])
                self.assertEqual(
                    result,
                    "file1 defined in symbol1\nfile1 used in symbol1\nfile1 defined in symbol1\nfile1 used in symbol1\n",
                )


def test_extract_degree_paths():
    graph = nx.DiGraph()
    graph.add_edge("file1", "symbol1")
    graph.add_edge("symbol1", "file2")
    result = extract_degree_paths(graph, "file1")
    assert result == [["file1", "symbol1", "file2"]]


def test_condense_paths():
    paths = [["file1", "symbol1", "file2"], ["file1", "symbol2", "file2"]]
    result = condense_paths(paths)
    assert result == [["file1", "symbol1, symbol2", "file2"]]


def test_extract_entities():
    code = (
        "import os\nclass Test:\n    pass\ndef test_func():\n    pass\nos.path.join()"
    )
    result = extract_entities(code)
    assert result == (["os", "join"], ["Test"], ["test_func"])


def test_traverse_folder():
    with patch("os.walk") as mock_walk, patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="import os\nclass Test:\n    pass\ndef test_func():\n    pass\nos.path.join()",
    ) as mock_file:
        mock_walk.return_value = [("root", [], ["file1.py"])]
        result = traverse_folder("root")
        assert isinstance(result[0], nx.DiGraph)
        assert isinstance(result[1], nx.DiGraph)


def test_draw_paths_on_graph():
    with patch("matplotlib.pyplot.show") as mock_show:
        graph = nx.DiGraph()
        graph.add_edge("file1", "symbol1")
        graph.add_edge("symbol1", "file2")
        draw_paths_on_graph(graph, [["file1", "symbol1", "file2"]])
        mock_show.assert_called_once()


def test_format_path():
    path = ["file1", "symbol1", "file2"]
    result = format_path(path)
    assert result == "symbol1 uses file2"


if __name__ == "__main__":
    unittest.main()
