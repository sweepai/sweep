from __future__ import annotations

import ast
import os
import re
import subprocess
import tempfile
import traceback
import uuid
from dataclasses import dataclass
from io import StringIO
from typing import Optional

import tiktoken
from pylint.lint import Run
from pylint.reporters.text import TextReporter
from tree_sitter import Node
from tree_sitter_languages import get_parser

from sweepai.core.entities import Snippet
from sweepai.logn import logger
from sweepai.utils.chat_logger import discord_log_error


def non_whitespace_len(s: str) -> int:  # new len function
    return len(re.sub("\s", "", s))


def get_line_number(index: int, source_code: str) -> int:
    total_chars = 0
    line_number = 0
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

    # 6. Coalescing last chunk if it's too small
    if len(line_chunks) > 1 and len(line_chunks[-1]) < coalesce:
        line_chunks[-2] += line_chunks[-1]
        line_chunks.pop()

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
    "cs": "cpp",
    "rb": "ruby",
    # "md": "markdown",
    # "rst": "markdown",
    # "txt": "markdown",
    # "erb": "embedded-template",
    # "ejs": "embedded-template",
    # "html": "embedded-template",
    "erb": "html",
    "ejs": "html",
    "html": "html",
    "vue": "html",
    "php": "php",
}


def naive_chunker(code: str, line_count: int = 30, overlap: int = 15):
    if overlap >= line_count:
        raise ValueError("Overlap should be smaller than line_count.")
    lines = code.split("\n")
    total_lines = len(lines)
    chunks = []

    start = 0
    while start < total_lines:
        end = min(start + line_count, total_lines)
        chunk = "\n".join(lines[start:end])
        chunks.append(chunk)
        start += line_count - overlap

    return chunks


def check_valid_typescript(code: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        file_hash = uuid.uuid4().hex[:10]
        tmp_file = os.path.join(temp_dir, file_hash + "_" + "temp.ts")

        with open(tmp_file, "w") as file:
            file.write(code)

        result = subprocess.run(
            ["npx", "prettier", "--parser", "babel-ts", tmp_file],
            capture_output=True,
        )

        os.remove(tmp_file)
        return result.returncode == 0, (result.stdout + result.stderr).decode("utf-8")


def check_syntax(file_path: str, code: str) -> tuple[bool, str]:
    ext = file_path.split(".")[-1]
    if ext in extension_to_language:
        language = extension_to_language[ext]
    else:
        return True, "Unsupported file extension, skipping syntax check."
    parser = get_parser(language)
    tree = parser.parse(code.encode("utf-8"))

    if language == "python":
        # First check for syntax errors
        try:
            ast.parse(code)
        except SyntaxError as e:
            error_message = f"Python syntax error: {e.msg} at line {e.lineno}"
            return False, error_message

    if ext in ("tsx", "ts"):
        is_valid, error_message = check_valid_typescript(code)
        if not is_valid:
            return is_valid, error_message

    def find_deepest_error(node: Node) -> Optional[Node]:
        deepest_error = None
        if node.has_error:
            deepest_error = node
        for child in node.children:
            child_error = find_deepest_error(child)
            if child_error:
                deepest_error = child_error
        return deepest_error

    error_location = find_deepest_error(tree.root_node)
    if error_location:
        line_number, _ = error_location.start_point
        error_start = max(0, line_number - 10)
        error_span = "\n".join(code.split("\n")[error_start:line_number])
        error_message = f"Invalid syntax found within or before the lines {error_start}-{line_number}, displayed below:\n{error_span}"
        return (False, error_message)
    return True, ""


def check_code(file_path: str, code: str) -> tuple[bool, str]:
    is_valid, error_message = check_syntax(file_path, code)
    if not is_valid:
        return is_valid, error_message
    ext = file_path.split(".")[-1]
    if ext == "py":
        file_hash = uuid.uuid4().hex
        new_file = os.path.join("/tmp", file_hash + "_" + os.path.basename(file_path))
        try:
            with open(new_file, "w") as f:
                f.write(code)
            pylint_output = StringIO()
            reporter = TextReporter(pylint_output)
            Run(
                [
                    new_file,
                    "--errors-only",
                    "--disable=import-error",
                    "--disable=no-member",
                    "--disable=relative-beyond-top-level",
                ],
                reporter=reporter,
                do_exit=False,
            )
            error_message = pylint_output.getvalue()
            try:
                os.remove(new_file)
            except FileNotFoundError:
                pass
            if error_message:
                return False, error_message
        except Exception as e:
            discord_log_error("Pylint BS:\n" + e + traceback.format_exc())
    return True, ""


def chunk_code(
    code: str, path: str, MAX_CHARS: int = 1500, coalesce: int = 100
) -> list[Snippet]:
    ext = path.split(".")[-1]
    if ext in extension_to_language:
        language = extension_to_language[ext]
    else:
        # Fallback to naive chunking if tree_sitter fails
        line_count = 30
        overlap = 15
        chunks = naive_chunker(code, line_count, overlap)
        snippets = []
        for idx, chunk in enumerate(chunks):
            new_snippet = Snippet(
                content=code,
                start=idx * (line_count - overlap),
                end=(idx + 1) * (line_count - overlap),
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
    except SystemExit:
        raise SystemExit
    except Exception:
        logger.error(traceback.format_exc())
        return []


TIKTOKEN_CACHE_DIR = "/tmp/cache/tiktoken"


class Tiktoken:
    openai_models = [
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-1106",
        "gpt-4",
        "gpt-4-32k",
        "gpt-4-32k-0613",
        "gpt-4-1106-preview",
    ]
    models = openai_models

    def __init__(self):
        self.openai_models = {
            model: tiktoken.encoding_for_model(model)
            for model in Tiktoken.openai_models
        }

    def count(self, text: str, model: str = "gpt-4") -> int:
        return len(self.openai_models[model].encode(text, disallowed_special=()))


test_code = """
import React from 'react';
import { render } from '@testing-library/react';
import CallToAction from '../components/CallToAction';
describe('CallToAction component', () => {
  it('renders the correct YouTube video link', () => {
    const { getByTitle } = render(<CallToAction />);
    const iframeElement = getByTitle('YouTube video player');
    expect(iframeElement.getAttribute('src')).toBe('https://www.youtube.com/embed/GVEkDZmWw8E?autoplay=1&mute=1&loop=1&vq=hd1080&modestbranding=1&controls=0');
    it('has a button with the correct color properties', () => {
    const { getByRole } = render(<CallToAction />);
    const buttonElement = getByRole('button', { name: /install sweep/i });
    expect(buttonElement).toHaveStyle({
      colorScheme: 'green',
      bg: 'green.400',
      _hover: { bg: 'green.600' }
    });
  });
});
"""


if __name__ == "__main__":
    print(check_syntax("CallToAction.test.tsx", test_code))
