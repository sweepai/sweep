import ast
import hashlib
from dataclasses import dataclass
from typing import Any

MIN_WINDOW_THRESHOLD = 10 # number of lines of code saved

@dataclass
class CodeWindow:
    code: str
    start_line: int
    end_line: int
    hash: str # should be computed based on the stripped and joined code

    def __eq__(self, __value: Any) -> bool:
        return self.hash == __value.hash
    
    def __len__(self) -> int:
        return self.end_line - self.start_line

def hash_content(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def get_sliding_windows(lines):
    result: list[CodeWindow] = []
    for window_size in range(3, len(lines) + 1):
        for i in range(len(lines) - window_size + 1):
            window = lines[i:i + window_size]
            window_code = "\n".join(window)
            stripped_code = "\n".join([line.strip() for line in window])
            hash = hash_content(stripped_code)
            result.append(CodeWindow(window_code, i, i + window_size, hash))
    return result

def get_refactor_snippets(code, hashes_dict):
    lines = [line for line in code.split("\n")]
    # create sliding windows and hash them
    windows = get_sliding_windows(lines)
    # construct a dictionary of all common windows and their total lengths
    for window in windows:
        if window.hash in hashes_dict:
            old_length = hashes_dict[window.hash][0][1]
            if old_length == 0:
                old_length += len(window)
            old_array = hashes_dict[window.hash][0][2]
            old_array.append((window.start_line, window.end_line))
            hashes_dict[window.hash] = [(window, old_length + len(window), old_array)]
        else:
            hashes_dict[window.hash] = [(window, 0, [(window.start_line, window.end_line)])]
    # sort the windows by length
    # filter out windows that are too short
    sorted_windows = sorted(hashes_dict.values(), key=lambda x: x[0][1], reverse=True)
    sorted_windows = [window[0] for window in sorted_windows if window[0][1] > MIN_WINDOW_THRESHOLD]
    completed_spans = [] # sections of the code that have already been complete
    final_window_code = []
    for window in sorted_windows:
        if overlap(window[2], completed_spans):
            continue
        if is_valid_window(code, window[0], window[2]):
            completed_spans.extend(window[2])
            final_window_code.append(window[0].code.lstrip())
    return final_window_code

def overlap(start_and_end_lines, completed_spans):
    for inner_start, inner_end in start_and_end_lines:
        for outer_start, outer_end in completed_spans:
            if outer_start <= inner_start < outer_end or outer_start < inner_end <= outer_end:
                return True
    return False

def is_valid_window(code: str, window: CodeWindow, start_and_end_indices: list[tuple[int, int]]):
    try:
        # parse the AST from the full code
        tree = ast.parse(code)
        # also try to parse the window, if it fails then we cannot proceed
        # remove indents first
        # get shortest common indent
        split_code = window.code.split("\n")
        shortest_common_indent = min([len(line) - len(line.lstrip()) for line in split_code if line.strip() != ""])
        tmp_window_code = "\n".join([line[shortest_common_indent:] for line in window.code.split("\n") if line.strip() != ""])
        ast.parse(tmp_window_code)
    except SyntaxError:
        # if there's a syntax error, we cannot proceed
        return False

    def node_within_start_and_end(node, start_and_end_indices):
        node_start_line = getattr(node, 'lineno', None)
        node_end_line = getattr(node, 'end_lineno', node_start_line)
        return any(start < node_start_line <= end or start <= node_end_line < end for start, end in start_and_end_indices)

    def contains_return_or_try(node, start_and_end_indices):
        for child in ast.walk(node):
            if isinstance(child, (ast.Return, ast.Try)) and node_within_start_and_end(child, start_and_end_indices):
                return True
        return False

    # check if the window is within any node that we want to ignore
    for node in ast.walk(tree):
        if contains_return_or_try(node, start_and_end_indices):
            return False
    # If we get here, the window is valid
    return True