from __future__ import annotations

import re
import traceback
from dataclasses import dataclass

import modal
from loguru import logger
from modal import method

from sweepai.config.env import UTILS_MODAL_INST_NAME, ENV
from sweepai.core.entities import Snippet


def non_whitespace_len(s: str) -> int:  # new len function
    return len(re.sub("\s", "", s))


def get_line_number(index: int, source_code: str) -> int:
    total_chars = 0
    for line_number, line in enumerate(source_code.splitlines(keepends=True), start=1):
        total_chars += len(line)
        if total_chars > index:
            return line_number - 1
    return line_number


@dataclass
class Span:
    # Represents a slice of a string
    start: int = 0
    end: int = 0

    def __post_init__(self):
        # If end is None, set it to start
        if self.end is None:
            self.end = self.start

    def extract(self, s: str) -> str:
        # Grab the corresponding substring of string s by bytes
        return s[self.start : self.end]

    def extract_lines(self, s: str) -> str:
        # Grab the corresponding substring of string s by lines
        return "\n".join(s.splitlines()[self.start : self.end])

    def __add__(self, other: Span | int) -> Span:
        # e.g. Span(1, 2) + Span(2, 4) = Span(1, 4) (concatenation)
        # There are no safety checks: Span(a, b) + Span(c, d) = Span(a, d)
        # and there are no requirements for b = c.
        if isinstance(other, int):
            return Span(self.start + other, self.end + other)
        elif isinstance(other, Span):
            return Span(self.start, other.end)
        else:
            raise NotImplementedError()

    def __len__(self) -> int:
        # i.e. Span(a, b) = b - a
        return self.end - self.start


def chunk_tree(
    tree,
    source_code: bytes,
    MAX_CHARS=512 * 3,
    coalesce=50,  # Any chunk less than 50 characters long gets coalesced with the next chunk
) -> list[Span]:
    from tree_sitter import Node

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
        return [Span(0, len(chunks[0]))]
    for prev, curr in zip(chunks[:-1], chunks[1:]):
        prev.end = curr.start
    curr.start = tree.root_node.end_byte

    # 3. Combining small chunks with bigger ones
    new_chunks = []
    current_chunk = Span(0, 0)
    for chunk in chunks:
        current_chunk += chunk
        if non_whitespace_len(
            current_chunk.extract(source_code.decode("utf-8"))
        ) > coalesce and "\n" in current_chunk.extract(source_code.decode("utf-8")):
            new_chunks.append(current_chunk)
            current_chunk = Span(chunk.end, chunk.end)
    if len(current_chunk) > 0:
        new_chunks.append(current_chunk)

    # 4. Changing line numbers
    line_chunks = [
        Span(
            get_line_number(chunk.start, source_code),
            get_line_number(chunk.end, source_code),
        )
        for chunk in new_chunks
    ]

    # 5. Eliminating empty chunks
    line_chunks = [chunk for chunk in line_chunks if len(chunk) > 0]
    return line_chunks


extension_to_language = {
    "js": "tsx",
    "jsx": "tsx",
    "ts": "tsx",
    "tsx": "tsx",
    "mjs": "tsx",
    "py": "python",
    "rs": "rust",
    "go": "go",
    "java": "java",
    "cpp": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "c": "cpp",
    "h": "cpp",
    "hpp": "cpp",
    "cs": "c-sharp",
    "rb": "ruby",
    "md": "markdown",
    "rst": "markdown",
    "txt": "markdown",
    "erb": "embedded-template",
    "ejs": "embedded-template",
    "html": "embedded-template",
    "vue": "vue",
    "php": "php",
}


def chunk_code(code: str, path: str, MAX_CHARS: int = 1500, coalesce: int = 100):
    from tree_sitter_languages import get_parser

    ext = path.split(".")[-1]
    if ext in extension_to_language:
        language = extension_to_language[ext]
    else:
        language = "python"
    try:
        parser = get_parser(language)
        tree = parser.parse(code.encode("utf-8"))
        chunks = chunk_tree(
            tree, code.encode("utf-8"), MAX_CHARS=MAX_CHARS, coalesce=coalesce
        )
        snippets = []
        for chunk in chunks:
            new_snippet = Snippet(
                content=chunk.extract_lines(code),
                start=chunk.start,
                end=chunk.end,
                file_path=path,
            )
            snippets.append(new_snippet)
        return snippets
    except Exception as e:
        logger.error(traceback.format_exc())
        return []


stub = modal.Stub(UTILS_MODAL_INST_NAME)
tiktoken_image = modal.Image.debian_slim().pip_install(
    "tiktoken", "loguru", "anthropic", "pyyaml", "PyGithub"
)

TIKTOKEN_CACHE_DIR = "/root/cache/tiktoken"
tiktoken_volume = modal.NetworkFileSystem.persisted("tiktoken-models")


@stub.cls(
    image=tiktoken_image,
    network_file_systems={TIKTOKEN_CACHE_DIR: tiktoken_volume},
    secret=modal.Secret.from_dict({"TIKTOKEN_CACHE_DIR": TIKTOKEN_CACHE_DIR}),
    keep_warm=5 if ENV == "prod" else 0,
    cpu=0.5,
)
class Tiktoken:
    openai_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-32k", "gpt-4-32k-0613"]
    anthropic_models = ["claude-v1", "claude-v1.3-100k", "claude-instant-v1.3-100k"]
    models = openai_models + anthropic_models

    def __enter__(self):
        import tiktoken

        self.openai_models = {
            model: tiktoken.encoding_for_model(model)
            for model in Tiktoken.openai_models
        }

    @method()
    def count(self, text: str, model: str = "gpt-4"):
        return len(self.openai_models[model].encode(text, disallowed_special=()))
