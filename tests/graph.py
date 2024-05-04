import multiprocessing
import os
import traceback

from loguru import logger
from tqdm import tqdm
from tree_sitter import Node
from sweepai.config.client import SweepConfig
from sweepai.core.entities import Snippet
from sweepai.core.repo_parsing_utils import FILE_THRESHOLD, filter_file, read_file
from sweepai.utils.timer import Timer
from sweepai.utils.utils import AVG_CHAR_IN_LINE, Span, get_line_number, get_parser, non_whitespace_len, naive_chunker, extension_to_language

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


def chunk_tree(
    tree,
    source_code: bytes,
    MAX_CHARS=AVG_CHAR_IN_LINE * 200,  # 200 lines of code
    coalesce=AVG_CHAR_IN_LINE * 50,  # 50 lines of code
) -> list[Span]:
    # 1. Recursively form chunks based on the last post (https://docs.sweep.dev/blogs/chunking-2m-files)
    def chunk_node(node: Node) -> list[Span]:
        chunks: list[Span] = []
        current_chunk: Span = Span(node.start_byte, node.start_byte)
        node_children = node.children
        for child in node_children:
            if child.end_byte - child.start_byte > MAX_CHARS:
                chunks.append(current_chunk)
                current_chunk = Span(child.end_byte, child.end_byte)
                chunks.extend(chunk_node(child))
            elif child.end_byte - child.start_byte + len(current_chunk) > MAX_CHARS:
                chunks.append(current_chunk)
                current_chunk = Span(child.start_byte, child.end_byte)
            else:
                current_chunk += Span(child.start_byte, child.end_byte)
        chunks.append(current_chunk)
        return chunks

    chunks = chunk_node(tree.root_node)

    # 2. Filling in the gaps
    if len(chunks) == 0:
        return []
    if len(chunks) < 2:
        end = get_line_number(chunks[0].end, source_code)
        return [Span(0, end)]
    for i in range(len(chunks) - 1):
        chunks[i].end = chunks[i + 1].start
    chunks[-1].end = tree.root_node.end_byte

    # 3. Combining small chunks with bigger ones
    new_chunks = []
    current_chunk = Span(0, 0)
    for chunk in chunks:
        current_chunk += chunk
        # if the current chunk starts with a closing parenthesis, bracket, or brace, we coalesce it with the previous chunk
        stripped_contents = current_chunk.extract(source_code.decode("utf-8")).strip()
        first_char = stripped_contents[0] if stripped_contents else ''
        if first_char in [")", "}", "]"] and new_chunks:
            new_chunks[-1] += chunk
            current_chunk = Span(chunk.end, chunk.end)
        # if the current chunk is too large, create a new chunk, otherwise, combine the chunks
        elif non_whitespace_len(
            current_chunk.extract(source_code.decode("utf-8"))
        ) > coalesce and "\n" in current_chunk.extract(source_code.decode("utf-8")):
            new_chunks.append(current_chunk)
            current_chunk = Span(chunk.end, chunk.end)
    if len(current_chunk) > 0:
        new_chunks.append(current_chunk)

    # 4. Changing line numbers
    first_chunk = new_chunks[0]
    line_chunks = [Span(0, get_line_number(first_chunk.end, source_code))]
    for chunk in new_chunks[1:]:
        start_line = get_line_number(chunk.start, source_code) + 1
        end_line = get_line_number(chunk.end, source_code)
        line_chunks.append(Span(start_line, max(start_line, end_line)))

    # 5. Eliminating empty chunks
    line_chunks = [chunk for chunk in line_chunks if len(chunk) > 0]

    # 6. Coalescing last chunk if it's too small
    if len(line_chunks) > 1 and len(line_chunks[-1]) < coalesce:
        line_chunks[-2] += line_chunks[-1]
        line_chunks.pop()

    return line_chunks

def file_path_to_chunks(file_path: str) -> list[str]:
    file_contents = read_file(file_path)
    chunks = chunk_code(file_contents, path=file_path)
    return chunks

def chunk_code(
    code: str,
    path: str,
    MAX_CHARS=AVG_CHAR_IN_LINE * 200,  # 200 lines of code
    coalesce=80,
) -> list[Snippet]:
    ext = path.split(".")[-1]
    if ext in extension_to_language:
        language = extension_to_language[ext]
    else:
        # Fallback to naive chunking if tree_sitter fails
        line_count = 50
        overlap = 0
        chunks = naive_chunker(code, line_count, overlap)
        snippets = []
        for idx, chunk in enumerate(chunks):
            end = min((idx + 1) * (line_count - overlap), len(code.split("\n")))
            new_snippet = Snippet(
                content=code,
                start=idx * (line_count - overlap),
                end=end,
                file_path=path,
            )
            snippets.append(new_snippet)
        return snippets
    try:
        parser = get_parser(language)
        tree = parser.parse(code.encode("utf-8"))
        chunks = chunk_tree(
            tree, code.encode("utf-8"), MAX_CHARS=MAX_CHARS, coalesce=coalesce
        )
        snippets = []
        for chunk in chunks:
            new_snippet = Snippet(
                content=code,
                start=chunk.start,
                end=chunk.end,
                file_path=path,
            )
            snippets.append(new_snippet)
        return snippets
    except Exception:
        logger.error(traceback.format_exc())
        return []

def directory_to_chunks(
    directory: str, sweep_config: SweepConfig
) -> tuple[list[Snippet], list[str]]:
    dir_file_count = {}

    def is_dir_too_big(file_name):
        dir_name = os.path.dirname(file_name)
        only_file_name = os.path.basename(dir_name)
        if only_file_name in ("node_modules", ".venv", "build", "venv", "patch"):
            return True
        if dir_name not in dir_file_count:
            dir_file_count[dir_name] = len(os.listdir(dir_name))
        return dir_file_count[dir_name] > FILE_THRESHOLD

    logger.info(f"Reading files from {directory}")
    vis = set()
    def dfs(file_path: str = directory):
        only_file_name = os.path.basename(file_path)
        if only_file_name in ("node_modules", ".venv", "build", "venv", "patch"):
            return
        if file_path in vis:
            return
        vis.add(file_path)
        if os.path.isdir(file_path):
            for file_name in os.listdir(file_path):
                for sub_file_path in dfs(os.path.join(file_path, file_name)):
                    yield sub_file_path
        else:
            yield file_path
    with Timer():
        file_list = dfs()
        file_list = [
            file_name
            for file_name in file_list
            if filter_file(directory, file_name, sweep_config)
            and os.path.isfile(file_name)
            and not is_dir_too_big(file_name)
        ]
    logger.info("Done reading files")
    all_chunks = []
    with multiprocessing.Pool(processes=multiprocessing.cpu_count() // 4) as pool:
        for chunks in tqdm(pool.imap(file_path_to_chunks, file_list), total=len(file_list)):
            all_chunks.extend(chunks)
    return all_chunks, file_list


ext_to_language_builtins = {"py": set(dir(str) + dir(list) + dir(__builtins__) + [attr for attr in dir(object)])}

def populate_function_definitions(file_path: str, node: Node, definitions_to_calls: dict[str, set[str]]):
    language_builtins = ext_to_language_builtins.get(file_path.split(".")[-1], set())
    if node.type == 'function_definition':
        function_name = node.child_by_field_name('name').text.decode()
        if function_name not in language_builtins:
            definition_location = f"{file_path}::{function_name}"
            definitions_to_calls[function_name] = set([definition_location])
        else:
            return
    # Recursively traverse child nodes
    for child in node.children:
        populate_function_definitions(file_path, child, definitions_to_calls)

def populate_function_usages(file_path: str, node: Node, definitions_to_calls: dict[str, set[str]]):
    # Traverse nodes to find function/method calls
    if node.type == 'call':
        called_node = node.child_by_field_name('function')
        # Function call
        called_name = called_node.text.decode()
        function_name = f"{called_name}"
        function_call_location = f"{file_path}::{node.parent.text.decode()}"

        if function_name in definitions_to_calls:
            definitions_to_calls[function_name].add(function_call_location)

    # Recursively traverse child nodes
    for child in node.children:
        populate_function_usages(file_path, child, definitions_to_calls)

def process_snippets(snippets: list[Snippet]):
    # Create a Tree-sitter parser
    parser = get_parser("python")

    # Create an empty graph
    definitions_to_calls: dict[str, set[str]] = {}

    # first pass to populate the definitions
    for snippet in tqdm(snippets):
        source_code = snippet.get_snippet(False, False)
        # truncate source code from snippet start to end
        file_path = snippet.file_path
        # Parse the source code
        tree = parser.parse(bytes(source_code, 'utf8'))
        root_node = tree.root_node
        populate_function_definitions(file_path, root_node, definitions_to_calls)
    # second pass to populate the usages
    for snippet in tqdm(snippets):
        source_code = snippet.get_snippet(False, False)
        # truncate source code from snippet start to end
        file_path = snippet.file_path
        # Parse the source code
        tree = parser.parse(bytes(source_code, 'utf8'))
        root_node = tree.root_node
        populate_function_usages(file_path, root_node, definitions_to_calls)

    return definitions_to_calls

# Example usage
repo_path = '/root/sweep/sweepai'

all_chunks, file_list = directory_to_chunks(repo_path, SweepConfig())
# all_chunks are the valid spans that we should match

definitions_to_calls = process_snippets(all_chunks)

print("total call nodes", len(list(definitions_to_calls.items())))
# histogram of the value lengths
lengths = [len(subset) for subset in definitions_to_calls.values()]

# Print the histogram
print_histogram(lengths)

# show the keys with length >= 12
sorted_keys = sorted(definitions_to_calls.keys(), key=lambda x: len(definitions_to_calls[x]))
for key in sorted_keys:
    if len(definitions_to_calls[key]) >= 12:
        print(key)

breakpoint()
# for some languages, we can use the imports to determine an eligible set of source definitions
# that will work for non-inherited class methods and break on inherited class methods