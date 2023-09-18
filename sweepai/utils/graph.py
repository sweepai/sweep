# Modifying the script to graph only the paths of degree 4 originating from a file.

import os
import ast
import networkx as nx
from networkx.drawing.layout import bipartite_layout
import matplotlib.pyplot as plt


def extract_degree_paths(graph, start_node, degree=3):
    paths = []

    def dfs(node, visited, path):
        if len(path) == degree:
            paths.append(path.copy())
            return
        for neighbor in graph.neighbors(node):
            if neighbor not in visited:
                visited.add(neighbor)
                dfs(neighbor, visited, path + [neighbor])
                visited.remove(neighbor)

    visited = set([start_node])
    dfs(start_node, visited, [start_node])
    return paths


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
                abs_path = os.path.join(root, file)
                rel_path = abs_path[len(folder) + 1 :]
                with open(abs_path, "r") as f:
                    code = f.read()
                imports, classes, functions = extract_entities(code)
                graph.add_node(rel_path)
                for imp in imports:
                    graph.add_edge(rel_path, imp)
                for cls in classes:
                    graph.add_edge(cls, rel_path)
                for func in functions:
                    graph.add_edge(func, rel_path)

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


def format_degree_4_path(path):
    return " -> ".join(path)


# class PythonCodeGraph:


if __name__ == "__main__":
    # Replace this with the actual path you want to traverse
    folder_path = "PATHTOSWEEP"
    graph = traverse_folder(folder_path)
    degree_4_paths = None
    draw_paths_on_graph(graph, degree_4_paths)
    # Select one file to extract degree 4 paths (you can loop over all files if needed)
    selected_file = ".py"  # Replace with actual file name in your folder

    # Extract degree 4 paths originating from the selected file
    degree_4_paths = extract_degree_paths(graph, selected_file)
    import pdb

    pdb.set_trace()
    res = ""

    for path in degree_4_paths:
        res += format_degree_4_path(path) + "\n"

    # Draw only those paths on the graph
