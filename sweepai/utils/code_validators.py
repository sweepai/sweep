from __future__ import annotations

import ast
from io import StringIO
import os
import re
import subprocess
from tempfile import TemporaryDirectory
import tempfile
import traceback
from dataclasses import dataclass
from typing import Optional
import uuid
import warnings

from pylint.lint import Run
from pylint.reporters.text import TextReporter
from loguru import logger
from tree_sitter import Node, Parser, Language
from tree_sitter_languages import get_parser as tree_sitter_get_parser
import tree_sitter_python
import tree_sitter_javascript

from sweepai.core.entities import Snippet
from sweepai.logn.cache import file_cache
from sweepai.utils.fuzzy_diff import patience_fuzzy_additions

warnings.simplefilter("ignore", category=FutureWarning)

AVG_CHAR_IN_LINE = 60

def get_parser(language: str):
    parser = Parser()
    if language in ("python", "py"):
        lang = Language(tree_sitter_python.language(), "python")
    elif language in ("javascript", "js"):
        lang = Language(tree_sitter_javascript.language(), "javascript")
    else:
        return tree_sitter_get_parser(language)
    parser.set_language(lang)
    return parser

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

def get_new_lint_errors_for_pylint(new_errors: str, old_errors: str) -> str:
    # Example of error: "main.py:1585:12: W0612: Unused variable 'command' (unused-variable)"
    additional_errors = patience_fuzzy_additions(old_errors, new_errors).splitlines()
    old_error_types = []
    for line in old_errors.splitlines():
        if line.count(" ") > 2:
            _file_delimiter, error_type, *_ = line.split(" ")
            old_error_types.append(error_type)
    results = []
    try:
        for line in additional_errors:
            if line.count(" ") >= 2: # sometimes the error doesn't have enough spaces, which raises an error
                _file_delimiter, error_type, *_ = line.split(" ")
            else:
                _file_delimiter, error_type = line.split(" ")
            if error_type.startswith("E") or old_error_types.count(error_type) < 2: # if there are more than 1 of the same error, we consider it new
                results.append(line)
    except Exception as e:
        logger.info(f"Error in get_new_lint_errors_for_pylint: {e}")
    return "\n".join(results)

def get_new_lint_errors_for_eslint(new_errors: str, old_errors: str) -> str:
    # Example of error: "main.py:1585:12: W0612: Unused variable 'command' (unused-variable)"
    additional_errors = patience_fuzzy_additions(old_errors, new_errors).splitlines()
    old_error_types = []
    for line in old_errors.splitlines():
        if line.count(" ") > 2:
            *_, error_type = line.split(" ")
            old_error_types.append(error_type)
    results = []
    for line in additional_errors:
        *_, error_type = line.split(" ")
        if not line.startswith("✖") and old_error_types.count(error_type) < 2: # if there are more than 1 of the same error, we consider it new
            results.append(line)
    return "\n".join(results)


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
        if other.parse_error_message:
            # Previously failing
            return ""
        if self.parse_error_message:
            return self.parse_error_message
        if len(self.pylint.splitlines()) > len(other.pylint.splitlines()):
            # return f"The code has the following pylint errors:\n\n{self.pylint}"
            new_pylint_errors = get_new_lint_errors_for_pylint(self.pylint, other.pylint)
            if not other.pylint:
                return f"The code has the following pylint errors:\n\n{self.pylint}"
            elif not new_pylint_errors:
                # All the errors are invalid
                return ""
            return f"The following new pylint errors have appeared:\n\n{new_pylint_errors}"
        if len(self.eslint.splitlines()) > len(other.eslint.splitlines()):
            new_eslint_errors = get_new_lint_errors_for_eslint(self.eslint, other.eslint)
            if not other.eslint:
                return f"The code has the following eslint errors:\n\n{self.eslint}"
            elif not new_eslint_errors:
                # All the errors are invalid
                return ""
            return f"The following new eslint errors have appeared:\n\n{new_eslint_errors}"
        return ""

def strip_ansi_codes(text: str) -> str:
    # ANSI escape sequences (color codes) are often starting with ESC ([) followed by some numbers and ends with "m".
    ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
    return ansi_escape.sub('', text)

def check_valid_typescript(file_path: str, code: str) -> tuple[bool, str]:
    is_valid = True
    message = ""
    version_check = ["tsc", "--version"]
    result = subprocess.run(
        " ".join(version_check),
        capture_output=True,
        text=True,
        shell=True,
    )
    # only run if tsc is available
    if result.returncode == 0:
        # Create a temporary file to hold the TypeScript code
        with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(code.encode('utf-8'))
        
        # Run `tsc` on the temporary file
        try:
            commands = ["tsc", "--pretty", "--noEmit", temp_file_path]
            result = subprocess.run(" ".join(commands), shell=True, text=True, capture_output=True)

            if result.returncode != 0:
                message = strip_ansi_codes(result.stdout)
                index = message.index(temp_file_path)
                full_temp_file_path = message[:index + len(temp_file_path)]
                message = message.replace(full_temp_file_path, file_path)

                # import error is TS2307 and should come up after the syntax check
                import_error = "error TS2307"
                if import_error in message:
                    num_of_errors = message.count(import_error)
                    # see if this matches the total amount of errors:
                    total_error_message = f"Found {num_of_errors} error"
                    if total_error_message in message:
                        # if we only have import errors, we consider it a successful check
                        return True, ""
                    else:
                        # there are more errors than just import errors
                        # now attempt to parse the message so that we remove import errors
                        message_lines = message.split("\n")
                        while num_of_errors > 0:
                            for line in message_lines:
                                if import_error in line:
                                    message_lines = message_lines[5:]
                                    num_of_errors -= 1
                        message = "\n".join(message_lines)
                return False, message
        finally:
            # Clean up: remove the temporary file
            os.remove(temp_file_path)
    return is_valid, message

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
    
    # we can't do this right now unfortunately as we don't have a way to mimic the production env for the code
    # if ext in ["ts"]:
    #     return check_valid_typescript(file_path, code)


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
        start_line, start_col = error_location.start_point
        end_line, end_col = error_location.end_point
        code_lines = code.split("\n")
        surrounding_lines = 3
        error_code_lines = code_lines[max(0, start_line - surrounding_lines):start_line]
        if start_line == end_line:
            error_code_lines += [code_lines[start_line]]
            error_code_lines += [" " * start_col + "^" * max(end_col - start_col, 1)]
        else:
            error_code_lines += ["=== ERROR START ==="]
            error_code_lines += code_lines[start_line:end_line + 1]
            error_code_lines += ["=== ERROR END ==="]
        error_code_lines += code_lines[end_line + 1:min(len(code_lines) - 1, end_line + surrounding_lines)]
        error_span = "\n".join(error_code_lines)
        if start_line == end_line:
            error_message = f"Invalid syntax found at line {start_line}, displayed below:\n{error_span}"
        else:
            error_message = f"Invalid syntax found from {start_line}-{end_line}, displayed below:\n{error_span}"
        return (False, error_message)
    return True, ""

# Need to add "no-unused-vars": "error"
# Need to add "import/first": "error"

DEFAULT_ESLINTRC = """{
    "parser": "@typescript-eslint/parser",
    "parserOptions": {
      "ecmaVersion": 2020,
      "sourceType": "module",
      "ecmaFeatures": {
        "jsx": true
      }
    },
    "settings": {
      "react": {
        "version": "detect"
      }
    },
    "extends": [
      "eslint:recommended",
      "plugin:react/recommended",
      "plugin:@typescript-eslint/recommended"
    ],
    "env": {
      "browser": true,
      "es2021": true,
      "node": true
    },
    "plugins": [
      "react",
      "@typescript-eslint"
    ],
    "rules": {
        "no-undef": "error",
        "no-const-assign": "error",
        "no-redeclare": "error",
        "no-unused-vars": "error",
        "no-use-before-define": ["error", { "functions": true, "classes": true, "variables": true }],
        "import/first": "error"
    }
  }
  """

pylint_args_non_last_fcr = [
    "--disable=C",
    "--enable=C0413", # Enable only the check for imports not at the top
    "--disable=W0611", # Don't check unused import
    "--disable=R",
    "--disable=import-error",
    "--disable=no-member",
]

# add a comment to all lines which are changed
pylint_args_last_fcr = [
    "--disable=C",
    "--enable=C0413",
    "--enable=W0611", # Check unused import
    "--disable=R",
    "--disable=import-error",
    "--disable=no-member",
]

@file_cache()
def get_pylint_check_results(file_path: str, code: str, last_fcr_for_file=False) -> CheckResults:
    logger.debug(f"Running pylint on {file_path}...")
    file_hash = uuid.uuid4().hex
    new_file = os.path.join("/tmp", file_hash + "_" + os.path.basename(file_path))
    stem = os.path.splitext(os.path.basename(file_path))[0]
    with open(new_file, "w") as f:
        f.write(code)
    pylint_output = StringIO()
    reporter = TextReporter(pylint_output)
    # this allows us to have a more rigorous check for the last file change request
    pylint_args = [new_file] + (pylint_args_last_fcr if last_fcr_for_file else pylint_args_non_last_fcr)
    Run(
        pylint_args,
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
    logger.debug("Done running pylint.")
    return CheckResults(pylint=error_message if not succeeded else "")

def get_check_results(file_path: str, code: str, last_fcr_for_file=False) -> CheckResults:
    is_valid, error_message = check_syntax(file_path, code)
    if not is_valid:
        return CheckResults(parse_error_message=error_message)
    ext = file_path.rsplit(".")[-1] # noqa
    if ext == "py":
        try:
            return get_pylint_check_results(file_path, code, last_fcr_for_file=last_fcr_for_file)
        except Exception as e:
            logger.exception(e)
    elif ext in ["js", "jsx", "ts", "tsx"]:
        # see if eslint is installed
        npx_commands = ["npx", "eslint", "--version"]
        try:
            result = subprocess.run(
                " ".join(npx_commands),
                timeout=5,
                capture_output=True,
                text=True,
                shell=True,
            )
        except subprocess.TimeoutExpired:
            raise Exception("ESLint timed out after 5s. You need eslint to edit js/ts files. Run `npm i -g eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin eslint-plugin-import eslint-plugin-react`.")
        # Check eslint < v9 and all the plugins exist
        if result.returncode == 0:
            with TemporaryDirectory(dir=os.getcwd()) as temp_dir:
                file_name = file_path.split(os.path.sep)[-1]
                new_file = os.path.join(temp_dir, f"{file_name}")
                config_file = os.path.join(temp_dir, ".eslintrc")
                with open(config_file, "w") as f:
                    f.write(DEFAULT_ESLINTRC)
                with open(new_file, "w") as f:
                    f.write(code)
                try:
                    eslint_commands = ["npx", "eslint", new_file, "--config", config_file, "--no-ignore"]
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

PRETTIERRC_FILES = [
    ".prettierrc",
    ".prettierrc.json",
    ".prettierrc.yaml",
    ".prettierrc.yml",
    ".prettierrc.js",
    "prettier.config.js",
]

def format_file(file_path: str, code: str, cwd: str | None = None) -> str:
    """
    Currently only supports JavaScript, TypeScript, and JSX.
    """
    file_name, ext = os.path.splitext(file_path)
    ext = ext.removeprefix(".")
    if ext in ("js", "jsx", "ts", "tsx"):
        prettier_config_path, prettier_config_contents = None, None
        for prettierrc_file in PRETTIERRC_FILES:
            full_path = os.path.join(cwd, prettierrc_file)
            if os.path.exists(full_path):
                # shutil.copy2(os.path.join(cwd, prettierrc_file), temp_dir)
                prettier_config_path = prettierrc_file
                with open(full_path, "r") as f:
                    prettier_config_contents = f.read()
                break
                
        if not prettier_config_path or not prettier_config_contents:
            return code

        with TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            """
            Check if there is a prettierrc file in the current directory and copy it to the temp directory.
            If there is no prettierrc file, return the original code.
            """
            with open(os.path.join(temp_dir, prettierrc_file), "w") as f:
                f.write(prettier_config_contents)
            npx_commands = ["npx", "prettier", "--stdin-filepath", file_path]
            try:
                result = subprocess.run(
                    " ".join(npx_commands),
                    input=code,
                    capture_output=True,
                    text=True,
                    shell=True,
                    cwd=temp_dir,
                )
                if result.returncode != 0:
                    logger.error(result.stderr)
                    return code
                return result.stdout
            except Exception as e:
                logger.error(e)
                return code
    return code

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
        line_count = MAX_CHARS // AVG_CHAR_IN_LINE
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


def get_function_name(file_name: str, source_code: str, line_number: int):
    ext = file_name.split(".")[-1]
    if ext in extension_to_language:
        language = extension_to_language[ext]
    else:
        return None
    type_mapping_per_language = {
        "python": "function_definition",
        "tsx": "function_declaration",
        "js": "function_declaration"
    }
    function_type_string = type_mapping_per_language.get(language)
    parser = get_parser(language)

    # Parse the source code
    tree = parser.parse(bytes(source_code, 'utf8'))

    # Get the root node of the syntax tree
    root_node = tree.root_node

    # Find the function node that contains the given line number
    function_node = root_node.descendant_for_point_range((line_number, 0), (line_number, 1))

    max_depth = 25 # Maximum depth to search for the function node
    while function_node.type != function_type_string:
        function_node = function_node.parent
        max_depth -= 1
        if max_depth == 0 or function_node is None:
            return None

    # Extract the function name
    function_name = function_node.child_by_field_name('name').text.decode('utf8')

    return function_name

def extract_definitions(file_name, code):
    ext = file_name.split(".")[-1]
    if ext in extension_to_language:
        language = extension_to_language[ext]
    else:
        return None

    type_mapping_per_language = {
        "typescript": ["class_declaration", "method_definition"],
        "tsx": ["function_declaration", "class_declaration", "method_definition"],
        "javascript": ["function_declaration", "class_declaration", "method_definition"]
    }
    function_type_strings = type_mapping_per_language.get(language)

    parser = get_parser(language)
    tree = parser.parse(bytes(code, "utf8"))

    def traverse_node(node):
        if node.type in function_type_strings:
            if node.type == "class_declaration":
                class_name = node.child_by_field_name("name").text.decode("utf8")
                print(f"Class: {class_name}")
            elif node.type == "function_declaration":
                function_name = node.child_by_field_name("name").text.decode("utf8")
                print(f"Function: {function_name}")
            elif node.type == "method_definition":
                method_name = node.child_by_field_name("name").text.decode("utf8")
                print(f"Method: {method_name}")

        for child in node.children:
            traverse_node(child)

    traverse_node(tree.root_node)

if __name__ == "__main__":
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
    typescript_code = """import {
    Flex,
    Container,
    Heading,
    Stack,
    Text,
    Button,
  } from "@chakra-ui/react";
  import { tsParticles } from "tsparticles";
  import { loadConfettiPreset } from "tsparticles-preset-confetti";
  import { useState } from "react";
  import logo from "../assets/icon.png";
  
  import ExternalLinkWithText from "./ExternalLinkWithText";
  import { TypeAnimation } from "react-type-animation";
  import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
  import { faUsers } from '@fortawesome/free-solid-svg-icons';
  const demo = require("../assets/demo.mp4");
  
export default function CallToAction() {
    const [spin, setSpin] = useState(false);
    // const canvas = document.getElementById('canvas3d');
    // const app = new Application(canvas);
    // app.load('https://prod.spline.design/jzV1MbbHCyCmMG7u/scene.splinecode');
    return (
      <Container maxW={"5xl"}>
      </Container>
    );
}
"""
    extract_definitions("main.tsx", typescript_code)
    breakpoint() # noqa
    python_code = """\
import math
import pandas

def get_circle_area(radius: float) -> float:
    return math.pi * radius ** 2
"""
    print(get_check_results("main.py", test_code))
    formatted_code = format_file("main.tsx", typescript_code, cwd="sweep_chat")
    function_name = get_function_name("main.ts", typescript_code, 20)
    print(function_name)
    function_name = get_function_name("main.py", python_code, 3)
    print(function_name)
    # new_code = """console.log("hello world")"""
    # check_results = check_syntax("test.js", new_code)
    check_results = get_check_results("test.tsx", typescript_code)
    check_results = get_check_results("test.py", python_code)
    assert check_results.pylint == "" # this should pass
    check_results = get_check_results("test.py", python_code, last_fcr_for_file=True)
    assert "Unused import pandas" in check_results.pylint # this should warn about unused imports