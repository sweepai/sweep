import ast
import hashlib
from dataclasses import dataclass
from typing import Any

from tqdm import tqdm

MIN_WINDOW_THRESHOLD = 10  # number of lines of code saved


@dataclass
class CodeWindow:
    code: str
    start_line: int
    end_line: int
    hash_: str  # should be computed based on the stripped and joined code

    def __eq__(self, __value: Any) -> bool:
        return self.hash_ == __value.hash

    def __len__(self) -> int:
        return self.end_line - self.start_line


def hash_content(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_sliding_windows(lines):
    for window_size in tqdm(range(3, min(len(lines) + 1, 50))[::-1]):
        for i in range(len(lines) - window_size + 1):
            window = lines[i : i + window_size]
            # check that the span contains >= 3 non-empty lines
            if len([line for line in window if line.strip() != ""]) < 3:
                continue
            window_code = "\n".join(window)
            stripped_code = "\n".join([line.strip() for line in window])
            hash_ = hash_content(stripped_code)
            yield CodeWindow(window_code, i, i + window_size, hash_)


def get_refactor_snippets(code, hashes_dict):
    lines = [line for line in code.split("\n")]
    active_vars = get_active_variables_per_line(code)
    for window in get_sliding_windows(lines):
        if window.hash_ in hashes_dict:
            old_length = hashes_dict[window.hash_][1]
            if old_length == len(window):
                old_length += len(lines) # duplicates count more
            old_array = hashes_dict[window.hash_][2]
            old_array.append((window.start_line, window.end_line))
            hashes_dict[window.hash_] = (window, old_length + len(window), old_array)
        else:
            hashes_dict[window.hash_] = (window, len(window), [(window.start_line, window.end_line)])
    sorted_windows = sorted(hashes_dict.values(), key=lambda x: x[1], reverse=True)
    sorted_windows = [
        window for window in sorted_windows if window[1] > MIN_WINDOW_THRESHOLD
    ]
    completed_spans = []  # sections of the code that have already been complete
    final_window_code = []
    non_dup_count = 0
    for window, window_value, start_and_end_indices in sorted_windows:
        if overlap(start_and_end_indices, completed_spans):
            continue
        if is_valid_window(code, window, start_and_end_indices):
            # not a duplicate, perform more rigorous checking
            if window_value < len(lines):
                # basically an integration over the active variables
                active_vars_delta = 0
                start_vars = active_vars.get(window.start_line, 0)
                for line in range(window.start_line, window.end_line):
                    if line in active_vars:
                        active_vars_delta += active_vars.get(line, 0) - start_vars
                if active_vars_delta >= 0:
                    non_dup_count += 1
                    completed_spans.extend(start_and_end_indices)
                    final_window_code.append(window.code.lstrip())
                    if non_dup_count > 2:
                        break
            else:
                completed_spans.extend(start_and_end_indices)
                final_window_code.append(window.code.lstrip())
    return final_window_code


def overlap(start_and_end_lines, completed_spans):
    for inner_start, inner_end in start_and_end_lines:
        for outer_start, outer_end in completed_spans:
            if (
                outer_start <= inner_start < outer_end
                or outer_start < inner_end <= outer_end
            ):
                return True
    return False


def is_valid_window(
    code: str, window: CodeWindow, start_and_end_indices: list[tuple[int, int]]
):
    try:
        # parse the AST from the full code
        tree = ast.parse(code)
        # also try to parse the window, if it fails then we cannot proceed
        # remove indents first
        # get shortest common indent
        split_code = window.code.split("\n")
        shortest_common_indent = min(
            [
                len(line) - len(line.lstrip())
                for line in split_code
                if line.strip() != ""
            ]
        )
        if shortest_common_indent == 0:
            # this handles the case when an envvar is defined, otherwise rope moves it out of scope
            return False
        # if the first or last line ends in a comma, do not proceed
        if split_code[0].strip().endswith(",") or split_code[-1].strip().endswith(","):
            return False
        window_code = "\n".join(
            [
                line[shortest_common_indent:]
                for line in window.code.split("\n")
                if line.strip() != ""
            ]
        )
        window_nodes = ast.parse(window_code).body
    except SyntaxError:
        # if there's a syntax error, we cannot proceed
        return False
    
    def node_within_start_and_end(node, start_and_end_indices):
        node_start_line = getattr(node, "lineno", None)
        node_end_line = getattr(node, "end_lineno", None)
        if node_start_line is None or node_end_line is None:
            return False
        return any(
            start < node_start_line <= end or start <= node_end_line < end
            for start, end in start_and_end_indices
        )

    def node_inside_invalid_entity(node, start_and_end_indices): # modify this later to remove cases when a function is defined inside
        for child in ast.walk(node):
            if isinstance(child, (ast.Return, ast.Try, ast.Import, ast.ImportFrom, ast.For)) and node_within_start_and_end(
                child, start_and_end_indices
            ):
                return True
        return False
    
    def invalid_entity_inside_node(window_nodes):
        if any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) for node in window_nodes):
                return True
        return False

    if invalid_entity_inside_node(window_nodes):
        return False

    # check if the window is within any node that we want to ignore
    for node in ast.walk(tree):
        if node_inside_invalid_entity(node, start_and_end_indices):
            return False
    # If we get here, the window is valid
    return True

def get_active_variables_per_line(code):
    # Parse the Python code into an AST
    parsed_code = ast.parse(code)

    # Helper function to traverse the AST and find the spans
    def find_usage_spans(node, usage_dict=None, parent_function=None):
        if usage_dict is None:
            usage_dict = {}
        
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Name):
                name = child.id
                if name not in usage_dict:
                    usage_dict[name] = {'first_used_line': child.lineno, 'last_used_line': child.lineno, 'parent_function': parent_function}
                else:
                    usage_dict[name]['last_used_line'] = child.lineno
            
            elif isinstance(child, ast.FunctionDef):
                parent_function = child.name
            
            find_usage_spans(child, usage_dict, parent_function)
        
        return usage_dict

    # Finding the usage spans
    usage_spans = find_usage_spans(parsed_code)
    return active_variables(usage_spans)

def active_variables(usage_spans):
    # Initialize a dictionary to count active variables per line
    active_vars = {}

    # Iterate through each variable and its span
    for var, spans in usage_spans.items():
        # If the variable is within a function, we'll only count it within that function's scope
        # for line in (spans['first_used_line'], spans['last_used_line'] + 1):
        for line in range(spans['first_used_line'], spans['last_used_line'] + 1):
        # for line in (spans['last_used_line'] + 1,):
            key = line
            if key in active_vars:
                active_vars[key].add(var)
            else:
                active_vars[key] = {var}
    
    # Convert sets to counts
    active_vars_counts = {key: len(vars) for key, vars in active_vars.items()}
    
    return active_vars_counts


if __name__ == "__main__":
    code = """"""
    refactor_snippets = get_refactor_snippets(code, {})
    active_vars = get_active_variables_per_line(code)
    print(active_vars)