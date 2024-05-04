import os
from sweepai.utils.utils import get_parser

def process_repository(repo_path):
    # Create a Tree-sitter parser
    parser = get_parser("python")

    # Create an empty graph
    graph = {}

    # Traverse the repository and process each file
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.endswith('.py'):  # Process Python files
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    source_code = f.read()

                # Parse the source code
                tree = parser.parse(bytes(source_code, 'utf8'))
                root_node = tree.root_node

                # Traverse the AST and extract function information
                def traverse(node):
                    if node.type == 'function_definition': # change this to anything but a call
                        function_name = node.child_by_field_name('name').text
                        function_key = f"{file_path}::{function_name}"
                        graph[function_key] = []

                    # Traverse nodes to find function calls
                    if node.type == 'call':
                        called_function = node.child_by_field_name('function').text
                        if called_function in graph:
                            graph[called_function].append(node.parent.text)
                        else:
                            graph[called_function] = [node.parent.text]

                    # Recursively traverse child nodes
                    for child in node.children:
                        traverse(child)

                traverse(root_node)
    return graph

# # Example usage
# repo_path = '/root/sweep/sweepai/utils/'
# function_graph = process_repository(repo_path)
# print(function_graph)
# # randomly sample a few non-empty key value pairs from the function_graph
# # and print them out
# sampled_items = [f"{k}   |   {v}" for k, v in function_graph.items() if v]
# print("\n".join(sampled_items[:5]))
# breakpoint()


def process_repository_v2(repo_path):
    # Create a Tree-sitter parser
    parser = get_parser("python")

    # Create an empty graph
    all_calls = {}
    all_definitions = {}

    # Traverse the repository and process each file
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.endswith('.py'):  # Process Python files
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    source_code = f.read()

                # Parse the source code
                tree = parser.parse(bytes(source_code, 'utf8'))
                root_node = tree.root_node

                # Traverse the AST and extract function and method information
                def traverse(node, class_name=None):
                    if node.type == 'class_definition':
                        class_name = node.child_by_field_name('name').text

                    if node.type == 'function_definition':
                        function_name = node.child_by_field_name('name').text
                        if class_name:
                            function_key = f"{file_path}::{class_name}.{function_name}"
                        else:
                            function_key = f"{file_path}::{function_name}"
                        graph[function_key] = []

                    # Traverse nodes to find function/method calls
                    if node.type == 'call':
                        called_node = node.child_by_field_name('function')
                        if called_node.type == 'attribute':
                            # Method call
                            object_name = called_node.child_by_field_name('object').text
                            method_name = called_node.child_by_field_name('attribute').text
                            called_key = f"{file_path}::{object_name}.{method_name}"
                        else:
                            # Function call
                            called_name = called_node.text
                            called_key = f"{file_path}::{called_name}"

                        if called_key in graph:
                            graph[called_key].append(node.parent.text)
                        else:
                            graph[called_key] = [node.parent.text]

                    # Recursively traverse child nodes
                    for child in node.children:
                        traverse(child, class_name)

                traverse(root_node)

    print([v for v in graph.values()])
    breakpoint()
    return graph

# Example usage
repo_path = '/root/sweep/sweepai/utils/'
function_graph = process_repository(repo_path)
print(function_graph)