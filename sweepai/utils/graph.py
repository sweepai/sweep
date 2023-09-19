# Modifying the script to graph only the paths of degree 4 originating from a file.

import os
import ast

from typing import Any

import networkx as nx
from networkx.drawing.layout import bipartite_layout
import matplotlib.pyplot as plt
from pydantic import BaseModel


def extract_degree_paths(graph, start_node, degree=3):
    paths = []

    def dfs(node, visited, path):
        if len(path) == degree:
            paths.append(path.copy())
            return
        if node not in graph:
            return
        for neighbor in graph.neighbors(node):
            if neighbor not in visited:
                visited.add(neighbor)
                dfs(neighbor, visited, path + [neighbor])
                visited.remove(neighbor)

    visited = set([start_node])
    dfs(start_node, visited, [start_node])
    return paths


def condense_paths(paths):
    # Path is File, Symbol, File
    # Condense to File, Symbol[], File if the files are the same
    condensed_path_dict = {}
    for path in paths:
        key = path[0] + "\n" + path[2]
        if key not in condensed_path_dict:
            condensed_path_dict[key] = [path[1]]
        else:
            condensed_path_dict[key].append(path[1])
    condensed_paths = []
    for key in condensed_path_dict:
        (path_1, path_2) = key.split("\n")
        condensed_paths.append([path_1, ", ".join(condensed_path_dict[key]), path_2])
    condensed_paths.sort(key=lambda x: len(x[1]), reverse=True)
    return condensed_paths


def extract_entities(code):
    tree = ast.parse(code)
    imported_modules = []
    defined_classes = []
    defined_functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            for n in node.names:
                imported_modules.append(n.name)
        elif isinstance(node, ast.ClassDef):
            defined_classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            defined_functions.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_functions.append(target.id)
    return imported_modules, defined_classes, defined_functions


def traverse_folder(folder): # TODO(add excluded_dirs)
    definitions_graph = nx.DiGraph()
    references_graph = nx.DiGraph()
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith(".py"):
                abs_path = os.path.join(root, file)
                rel_path = abs_path[len(folder) + 1 :]
                with open(abs_path, "r") as f:
                    code = f.read()
                imports, classes, functions = extract_entities(code)
                definitions_graph.add_node(rel_path)
                references_graph.add_node(rel_path)
                for imp in imports:
                    definitions_graph.add_edge(rel_path, imp)
                    references_graph.add_edge(imp, rel_path)
                for cls in classes:
                    definitions_graph.add_edge(cls, rel_path)
                    references_graph.add_edge(rel_path, cls)
                for func in functions:
                    definitions_graph.add_edge(func, rel_path)
                    references_graph.add_edge(rel_path, func)

    def remove_nodes(graph):
        # Removing entities that do not point to a file
        file_nodes = [n for n in graph.nodes if n.endswith(".py")]
        non_file_nodes = set(graph.nodes) - set(file_nodes)
        entities_to_remove = [
            n
            for n in non_file_nodes
            if not any(graph.has_edge(n, f) for f in file_nodes)
        ]
        graph.remove_nodes_from(entities_to_remove)

        # Removing files with a total degree of 0
        file_nodes_to_remove = [
            f for f, degree in graph.degree(file_nodes) if degree == 0
        ]
        graph.remove_nodes_from(file_nodes_to_remove)

        # Pruning nodes based on the sum of in-degree and out-degree
        nodes_to_remove = [node for node, degree in graph.degree() if degree <= 1]
        graph.remove_nodes_from(nodes_to_remove)

        # Remove non-file nodes with in-degree 0 at the end
        non_file_nodes_to_remove = [
            n for n, degree in graph.in_degree(non_file_nodes) if degree == 0
        ]
        graph.remove_nodes_from(non_file_nodes_to_remove)

        # Remove files with total-degree 0 at the end
        file_nodes_to_remove = [
            f for f, degree in graph.degree(file_nodes) if degree == 0
        ]
        graph.remove_nodes_from(file_nodes_to_remove)

    remove_nodes(definitions_graph)
    remove_nodes(references_graph)

    return definitions_graph, references_graph


def draw_paths_on_graph(graph, paths=None):
    if paths:
        subgraph_nodes = set([node for path in paths for node in path])
        subgraph = graph.subgraph(subgraph_nodes)
    else:
        subgraph = graph
    file_nodes = [n for n in subgraph.nodes if n.endswith(".py")]
    pos = bipartite_layout(subgraph, nodes=file_nodes)

    edge_labels = {(u, v): f"{u} -> {v}" for u, v in subgraph.edges()}
    nx.draw(
        subgraph,
        pos,
        with_labels=True,
        node_color="skyblue",
        font_size=10,
        font_color="black",
    )
    nx.draw_networkx_edge_labels(subgraph, pos, edge_labels=edge_labels, font_size=8)
    plt.show()


def format_path(path, separator=" uses "):
    return separator.join(path[1:])


class Graph(BaseModel):
    definitions_graph: Any
    references_graph: Any

    @classmethod
    def from_folder(cls, folder_path):
        definitions_graph, references_graph = traverse_folder(folder_path)
        return cls(
            definitions_graph=definitions_graph, references_graph=references_graph
        )

    def extract_first_degree(self, file_path: str) -> str:
        definition_paths = self.find_definitions(file_path)
        references_path = self.find_references(file_path)

        condensed_definition_paths = condense_paths(definition_paths)
        condensed_references_paths = condense_paths(references_path)

        res = ""
        for path in condensed_definition_paths:
            res += format_path(path, separator=" defined in ") + "\n"
        for path in condensed_references_paths:
            res += format_path(path, separator=" used in ") + "\n"
        return res

    def find_definitions(self, file_path: str):
        definition_paths = extract_degree_paths(self.definitions_graph, file_path)
        return definition_paths

    def find_references(self, file_path: str):
        references_path = extract_degree_paths(self.references_graph, file_path)
        return references_path

    def paths_to_first_degree_entities(self, file_paths: list[str]):
        return "\n".join([self.extract_first_degree(file_path) for file_path in file_paths])


g = Graph()


if __name__ == "__main__":
    # Replace this with the actual path you want to traverse
    folder_path = os.getcwd()
    definitions_graph, references_graph = traverse_folder(folder_path)

    # Select one file to extract degree 4 paths (you can loop over all files if needed)
    selected_files = (
        "sweepai/core/code_repair.py",
        "sweepai/core/sweep_bot.py",
        "sweepai/core/chat.py",
        "sweepai/core/prompts.py",
    )

    def get_entities_for_file(selected_file):
        definition_paths = extract_degree_paths(definitions_graph, selected_file)
        references_path = extract_degree_paths(references_graph, selected_file)

        condensed_definition_paths = condense_paths(definition_paths)
        condensed_references_paths = condense_paths(references_path)
        res = ""

        for path in condensed_definition_paths:
            res += format_path(path, separator=" defined in ") + "\n"
        for path in condensed_references_paths:
            res += format_path(path, separator=" imported by ") + "\n"
        return res

    print(
        "\n".join(
            [get_entities_for_file(selected_file) for selected_file in selected_files]
        )
    )
    # Draw only those paths on the graph
