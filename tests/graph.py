import os

from tqdm import tqdm
from sweepai.utils.utils import get_parser

from collections import Counter

def print_histogram(data):
    counter = Counter(data)
    max_count = max(counter.values())
    max_key_length = max(len(str(key)) for key in counter.keys())

    for key, count in sorted(counter.items()):
        bar_length = int(count / max_count * 50)
        bar = '█' * bar_length
        key_str = str(key).rjust(max_key_length)
        print(f"{key_str} | {bar} ({count})")

def process_repository(repo_path):
    # Create a Tree-sitter parser
    parser = get_parser("python")

    # Create an empty graph
    all_calls = {}
    all_definitions = {}

    # Traverse the repository and process each file
    for root, _, files in tqdm(os.walk(repo_path)):
        
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
                        class_name = node.child_by_field_name('name').text.decode()
                        class_name = str(class_name)

                    if node.type == 'function_definition':
                        function_name = node.child_by_field_name('name').text.decode()
                        if class_name:
                            definition_location = f"{file_path}::{class_name}.{function_name}"
                        else:
                            definition_location = f"{file_path}::{function_name}"
                        all_definitions[function_name] = definition_location # todo: add the source code of the definition

                    # Traverse nodes to find function/method calls
                    if node.type == 'call':
                        called_node = node.child_by_field_name('function')
                        # Function call
                        called_name = called_node.text.decode()
                        called_key = f"{called_name}"
                        called_value = f"{file_path}::{node.parent.text.decode()}"

                        if called_key in all_calls:
                            all_calls[called_key].append(called_value)
                        else:
                            all_calls[called_key] = [called_value]

                    # Recursively traverse child nodes
                    for child in node.children:
                        traverse(child, class_name)

                traverse(root_node)

    return all_calls, all_definitions

# Example usage
repo_path = '/root/sweep/sweepai'
all_calls, all_definitions = process_repository(repo_path)
# try resolving the calls to definitions
# the keys in all_definitions are the keys in all_calls, build a value to value dict from all_definitions to all_calls

definitions_to_calls = {}
for key, call_locations in all_calls.items():
    if key in all_definitions:
        definitions_to_calls[all_definitions[key]] = call_locations

print("total call nodes", len(list(definitions_to_calls.items())))
# histogram of the value lengths
lengths = [len(sublist) for sublist in definitions_to_calls.values()]


# Print the histogram
print_histogram(lengths)

# show the keys with length >= 12
for key, value in definitions_to_calls.items():
    if len(value) >= 12:
        print(key)

breakpoint()

# for some languages, we can use the imports to determine an eligible set of source definitions
# that will work for non-inherited class methods and break on inherited class methods