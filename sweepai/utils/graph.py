# Modifying the script to remove non-file nodes with in-degree 0 at the end.

import os
import ast
import networkx as nx
from networkx.drawing.layout import bipartite_layout
import matplotlib.pyplot as plt


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
    return imported_modules, defined_classes, defined_functions


def traverse_folder(folder):
    graph = nx.DiGraph()
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath, "r") as f:
                    code = f.read()
                imports, classes, functions = extract_entities(code)
                graph.add_node(file)
                for imp in imports:
                    graph.add_edge(file, imp)
                for cls in classes:
                    graph.add_edge(cls, file)
                for func in functions:
                    graph.add_edge(func, file)

    # Removing entities that do not point to a file
    file_nodes = [n for n in graph.nodes if n.endswith(".py")]
    non_file_nodes = set(graph.nodes) - set(file_nodes)
    entities_to_remove = [
        n for n in non_file_nodes if not any(graph.has_edge(n, f) for f in file_nodes)
    ]
    graph.remove_nodes_from(entities_to_remove)

    # Removing files with a total degree of 0
    file_nodes_to_remove = [f for f, degree in graph.degree(file_nodes) if degree == 0]
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
    file_nodes_to_remove = [f for f, degree in graph.degree(file_nodes) if degree == 0]
    graph.remove_nodes_from(file_nodes_to_remove)

    return graph


def draw_bipartite_graph_with_labels(graph):
    file_nodes = [n for n in graph.nodes if n.endswith(".py")]
    pos = bipartite_layout(graph, nodes=file_nodes)
    edge_labels = {(u, v): f"{u} -> {v}" for u, v in graph.edges()}
    nx.draw(
        graph,
        pos,
        with_labels=True,
        node_color="skyblue",
        font_size=10,
        font_color="black",
    )
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=8)
    plt.show()


if __name__ == "__main__":
    # Replace this with the actual path you want to traverse
    folder_path = os.getcwd() + "/sweepai/core"
    graph = traverse_folder(folder_path)
    draw_bipartite_graph_with_labels(graph)
