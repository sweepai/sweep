from __future__ import annotations

import ast
from io import StringIO
import os
import re
import subprocess
from tempfile import TemporaryDirectory
import traceback
from dataclasses import dataclass
from typing import Optional
import uuid

from pylint.lint import Run
from pylint.reporters.text import TextReporter
import tiktoken
from loguru import logger
from tree_sitter import Node
from tree_sitter_languages import get_parser

from sweepai.core.entities import Snippet
from sweepai.utils.fuzzy_diff import patience_fuzzy_diff


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
        return "\n".join(s.splitlines()[self.start : self.end + 1])

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


AVG_CHAR_IN_LINE = 60


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
    "elm": "elm",
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

@dataclass
class CheckResults:
    # Experimental feature, we'll see how this does.
    # TODO: smart parsing
    parse_error_message: str = ""
    pylint: str = ""
    eslint: str = ""

    def is_worse_than(self, other: CheckResults) -> bool:
        if self.parse_error_message:
            return True
        if other.parse_error_message:
            return False
        return len(self.pylint.splitlines()) > len(other.pylint.splitlines()) or len(self.eslint.splitlines()) > len(other.eslint.splitlines())
    
    def is_worse_than_message(self, other: CheckResults) -> str:
        if self.parse_error_message:
            return self.parse_error_message
        if other.parse_error_message:
            return other.parse_error_message
        if len(self.pylint.splitlines()) > len(other.pylint.splitlines()):
            # return f"The code has the following pylint errors:\n\n{self.pylint}"
            if not other.pylint:
                return f"The code has the following pylint errors:\n\n{self.pylint}"
            return f"The following new pylint errors have appeared. Here is the diff:\n\n{patience_fuzzy_diff(other.pylint, self.pylint)}"
        if len(self.eslint.splitlines()) > len(other.eslint.splitlines()):
            if not other.eslint:
                return f"The code has the following eslint errors:\n\n{self.eslint}"
            return f"The following new eslint errors have appeared. Here is the diff:\n\n{patience_fuzzy_diff(other.eslint, self.eslint)}"
        return ""


def check_valid_typescript(code: str) -> tuple[bool, str]:
    # with tempfile.TemporaryDirectory() as temp_dir:
    #     file_hash = uuid.uuid4().hex[:10]
    #     tmp_file = os.path.join(temp_dir, file_hash + "_" + "temp.ts")

    #     with open(tmp_file, "w") as file:
    #         file.write(code)

    #     result = subprocess.run(
    #         ["npx", "prettier", "--parser", "babel-ts", tmp_file],
    #         capture_output=True,
    #         timeout=5,
    #     )

    #     os.remove(tmp_file)
    #     return result.returncode == 0, (result.stdout + result.stderr).decode("utf-8")
    return True, ""

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
        start = error_location.start_point
        end = error_location.end_point
        error_code_lines = code.split("\n")[start[0]:end[0]]
        error_code_lines[0] = error_code_lines[0][start[1]:]
        error_code_lines[-1] = error_code_lines[-1][:end[1]]
        error_span = "\n".join(error_code_lines)
        if start[0] == end[0]:
            error_message = f"Invalid syntax found at line {start[0]}, displayed below:\n{error_span}"
        else:
            error_message = f"Invalid syntax found from {start}-{end}, displayed below:\n{error_span}"
        return (False, error_message)
    return True, ""

# Need to add "no-unused-vars": "error"
# Need to add "import/first": "error"

DEFAULT_ESLINTRC = """{
  "parser": "@typescript-eslint/parser",
  "parserOptions": {
    "ecmaVersion": 2020,
    "sourceType": "module"
  },
  "plugins": [
    "@typescript-eslint",
    "import"
  ],
  "rules": {
    "no-undef": "error",
    "no-const-assign": "error",
    "no-redeclare": "error",
    "no-unused-vars": "error",
    "no-use-before-define": ["error", { "functions": true, "classes": true, "variables": true }],
    "import/first": "error"
  },
  "settings": {
    "import/resolver": {
      "typescript": {}
    }
  },
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:import/typescript"
  ],
  "overrides": [
    {
      "files": ["*.ts", "*.tsx"],
      "rules": {
        "no-undef": "off"
      }
    }
  ]
}"""

def get_check_results(file_path: str, code: str) -> CheckResults:
    is_valid, error_message = check_syntax(file_path, code)
    if not is_valid:
        return CheckResults(parse_error_message=error_message)
    ext = file_path.split(".")[-1] # noqa
    if ext == "py":
        file_hash = uuid.uuid4().hex
        new_file = os.path.join("/tmp", file_hash + "_" + os.path.basename(file_path))
        stem = os.path.splitext(os.path.basename(file_path))[0]
        try:
            with open(new_file, "w") as f:
                f.write(code)
            pylint_output = StringIO()
            reporter = TextReporter(pylint_output)
            Run(
                [
                    new_file,
                    "--disable=C",
                    "--enable=C0413",  # Enable only the check for imports not at the top
                    "--disable=R",
                    "--disable=import-error",
                    "--disable=no-member",
                    "--disable=unused-import" # we have a workaround for this tbh
                ],
                reporter=reporter,
                exit=False,
            )
            error_message = pylint_output.getvalue().strip()
            try:
                os.remove(new_file)
            except FileNotFoundError:
                pass
            succeeded = error_message.startswith("------------------------------------")
            if error_message:
                error_message = error_message.replace(new_file, file_path).replace(f"{file_hash}_" + stem, stem)
                error_message = error_message.split("-----------------------------------", 1)[0].strip()
                error_message = f"> pylint {file_path}\n\n" + error_message
            return CheckResults(pylint=error_message if not succeeded else "")
        except Exception as e:
            logger.exception(e)
    if ext == "ts":
        # see if eslint is installed
        npx_commands = ["npx", "eslint", "--version"]
        result = subprocess.run(
            " ".join(npx_commands),
            capture_output=True,
            text=True,
            shell=True,
        )
        if result.returncode == 0:
            with TemporaryDirectory() as temp_dir:
                new_file = os.path.join(temp_dir, "temp.ts")
                with open(os.path.join(temp_dir, ".eslintrc"), "w") as f:
                    f.write(DEFAULT_ESLINTRC)
                with open(new_file, "w") as f:
                    f.write(code)
                try:
                    eslint_commands = ["npx", "eslint", new_file]
                    result = subprocess.run(
                        " ".join(eslint_commands),
                        capture_output=True,
                        text=True,
                        shell=True,
                        timeout=30,
                    )
                    error_message = (result.stdout + "\n\n" + result.stderr).strip().replace(new_file, file_path)
                    return CheckResults(eslint=error_message)
                except subprocess.TimeoutExpired:
                    logger.warning(f"ESLint timed out after 30s for {file_path}")
                    pass
    return CheckResults()

def check_code(file_path: str, code: str) -> tuple[bool, str]:
    is_valid, error_message = check_syntax(file_path, code)
    if not is_valid:
        return is_valid, error_message
    ext = file_path.split(".")[-1] # noqa
    if ext == "py":
        file_hash = uuid.uuid4().hex
        new_file = os.path.join("/tmp", file_hash + "_" + os.path.basename(file_path))
        stem = os.path.splitext(os.path.basename(file_path))[0]
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
                exit=False,
            )
            error_message = pylint_output.getvalue().strip()
            try:
                os.remove(new_file)
            except FileNotFoundError:
                pass
            if not error_message.startswith("------------------------------------"):
                error_message = error_message.replace(new_file, file_path).replace(f"{file_hash}_" + stem, stem)
                error_message = error_message.split("-----------------------------------", 1)[0].strip()
                error_message = f"> pylint {file_path}\n\n" + error_message
                return False, error_message
        except Exception as e:
            logger.exception(e)
    if ext == "ts":
        # see if eslint is installed
        result = subprocess.run(
            ["npx", "eslint", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            with TemporaryDirectory() as temp_dir:
                new_file = os.path.join(temp_dir, "temp.ts")
                with open(os.path.join(temp_dir, ".eslintrc"), "w") as f:
                    f.write(DEFAULT_ESLINTRC)
                with open(new_file, "w") as f:
                    f.write(code)
                result = subprocess.run(
                    ["npx", "eslint", new_file, "--config", ".eslintrc"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    return False, result.stdout + "\n\n" + result.stderr
    return True, ""


# @file_cache()
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
    except SystemExit:
        raise SystemExit
    except Exception:
        logger.error(traceback.format_exc())
        return []


TIKTOKEN_CACHE_DIR = "/tmp/cache/tiktoken"


class Tiktoken:
    def __init__(self):
        openai_models = [
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-1106",
            "gpt-4",
            "gpt-4-32k",
            "gpt-4-32k-0613",
            "gpt-4-1106-preview",
            "gpt-4-0125-preview",
        ]
        self.openai_models = {
            model: tiktoken.encoding_for_model(model) for model in openai_models
        }

    def count(self, text: str, model: str = "gpt-4") -> int:
        return len(self.openai_models[model].encode(text, disallowed_special=()))

    def truncate_string(
        self, text: str, model: str = "gpt-4", max_tokens: int = 8192
    ) -> str:
        tokens = self.openai_models[model].encode(text)[:max_tokens]
        return self.openai_models[model].decode(tokens)


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

test_code = """
x = "test"

import numpy
"""

if __name__ == "__main__":
    # print(check_code("main.tsx", test_code))
    # print(get_check_results("main.py", test_code))
    code = """import { isPossiblyValidEmail } from '../validation-utils'
import { PulseValidationException } from '../pulse-exceptions'

export function getEmailDomain (email: string): string {
  if (!isPossiblyValidEmail(email)) {
    throw new PulseValidationException(`Email is invalid: ${email}`)
  }
  // Emails are tough. An email can contain multiple '@' symbols.
  // Thankfully, domains cannot contain @, so the domain will be
  // part after the last @ in the email.
  // e.g., "steve@macbook"@trilogy.com is a valid email.
  //
  const tokens = email.split('@')
  return tokens[tokens.length - 1].toLowerCase().trim()
}

export function removeEmailAlias(email: string): string {
  if (!isPossiblyValidEmail(email)) {
    throw new PulseValidationException(`Email is invalid: ${email}`)
  
  const atIndex = email.lastIndexOf('@')
  const aliasIndex = email.lastIndexOf('+', atIndex)

  if (aliasIndex > 0) {
    return email.substring(0, aliasIndex) + email.substring(atIndex)
  }

  return email
}"""
    check_results = get_check_results("test.ts", code)
    import pdb
    # pylint: disable=no-member
    pdb.set_trace()
