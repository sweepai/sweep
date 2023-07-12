import os
import re
import subprocess
from dataclasses import dataclass

import modal
from loguru import logger
from modal import method

from sweepai.utils.config.server import UTILS_MODAL_INST_NAME

stub = modal.Stub(UTILS_MODAL_INST_NAME)
tiktoken_image = modal.Image.debian_slim().pip_install("tiktoken", "loguru", "anthropic", "pyyaml", "PyGithub")

TIKTOKEN_CACHE_DIR = "/root/cache/tiktoken"
tiktoken_volume = modal.SharedVolume().persist("tiktoken-models")


@stub.cls(
    image=tiktoken_image,
    shared_volumes={TIKTOKEN_CACHE_DIR: tiktoken_volume},
    secret=modal.Secret.from_dict({"TIKTOKEN_CACHE_DIR": TIKTOKEN_CACHE_DIR})
)
class Tiktoken:
    openai_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-32k", "gpt-4-32k-0613"]
    anthropic_models = ["claude-v1", "claude-v1.3-100k", "claude-instant-v1.3-100k"]
    models = openai_models + anthropic_models

    def __enter__(self):
        import tiktoken
        self.openai_models = {model: tiktoken.encoding_for_model(model) for model in Tiktoken.openai_models}

    @method()
    def count(self, text: str, model: str = "gpt-4"):
        return len(self.openai_models[model].encode(text))


chunking_image = modal.Image.debian_slim() \
    .apt_install("git") \
    .pip_install("tree-sitter", "loguru", "pyyaml", "PyGithub")

CHUNKING_CACHE_DIR = "/root/cache/"
chunking_volume = modal.SharedVolume().persist("chunking-parsers")


@dataclass
class Span:
    start: int
    end: int

    def extract(self, s: str) -> str:
        return "\n".join(s.splitlines()[self.start:self.end])

    def __add__(self, other):
        if isinstance(other, int):
            return Span(self.start + other, self.end + other)
        elif isinstance(other, Span):
            return Span(self.start, other.end)
        else:
            raise NotImplementedError()

    def __len__(self):
        return self.end - self.start


def get_line_number(index: int, source_code: str) -> int:
    # unoptimized, use binary search
    lines = source_code.splitlines(keepends=True)
    total_chars = 0
    line_number = 0
    while total_chars <= index:
        if line_number == len(lines):
            return line_number
        total_chars += len(lines[line_number])
        line_number += 1
    return line_number - 1


def chunker(tree, source_code_bytes, max_chunk_size=512 * 3, coalesce=50):
    # Recursively form chunks with a maximum chunk size of max_chunk_size
    def chunker_helper(node, source_code_bytes, start_position=0):
        chunks = []
        current_chunk = Span(start_position, start_position)
        for child in node.children:
            child_span = Span(child.start_byte, child.end_byte)
            if len(child_span) > max_chunk_size:
                chunks.append(current_chunk)
                chunks.extend(chunker_helper(child, source_code_bytes, child.start_byte))
                current_chunk = Span(child.end_byte, child.end_byte)
            elif len(current_chunk) + len(child_span) > max_chunk_size:
                chunks.append(current_chunk)
                current_chunk = child_span
            else:
                current_chunk += child_span
        if len(current_chunk) > 0:
            chunks.append(current_chunk)
        return chunks

    chunks = chunker_helper(tree.root_node, source_code_bytes)

    # removing gaps
    for prev, curr in zip(chunks[:-1], chunks[1:]):
        prev.end = curr.start

    # combining small chunks with bigger ones
    new_chunks = []
    i = 0
    current_chunk = Span(0, 0)
    while i < len(chunks):
        current_chunk += chunks[i]
        if count_length_without_whitespace(
                source_code_bytes[current_chunk.start:current_chunk.end].decode("utf-8")) > coalesce \
                and "\n" in source_code_bytes[current_chunk.start:current_chunk.end].decode("utf-8"):
            new_chunks.append(current_chunk)
            current_chunk = Span(chunks[i].end, chunks[i].end)
        i += 1
    if len(current_chunk) > 0:
        new_chunks.append(current_chunk)

    line_chunks = [Span(get_line_number(chunk.start, source_code=source_code_bytes),
                        get_line_number(chunk.end, source_code=source_code_bytes)) for chunk in new_chunks]
    line_chunks = [chunk for chunk in line_chunks if len(chunk) > 0]

    return line_chunks


def count_length_without_whitespace(s: str):
    string_without_whitespace = re.sub(r'\s', '', s)
    return len(string_without_whitespace)


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


@stub.cls(
    image=chunking_image,
    shared_volumes={CHUNKING_CACHE_DIR: chunking_volume},
)
class Chunking:

    def __enter__(self):
        from tree_sitter import Language

        logger.debug("Downloading tree-sitter parsers")

        LANGUAGE_NAMES = ["python", "java", "cpp", "go", "rust", "ruby", "php"]
        for language in LANGUAGE_NAMES:
            subprocess.run(
                f"git clone https://github.com/tree-sitter/tree-sitter-{language} cache/tree-sitter-{language}",
                shell=True)
        for language in LANGUAGE_NAMES:
            Language.build_library(f'cache/build/{language}.so', [f"cache/tree-sitter-{language}"])
            subprocess.run(f"cp cache/build/{language}.so /tmp/{language}.so", shell=True)  # copying for executability
        self.languages = {language: Language(f"/tmp/{language}.so", language) for language in LANGUAGE_NAMES}

        subprocess.run(f"git clone https://github.com/tree-sitter/tree-sitter-typescript cache/tree-sitter-typescript",
                       shell=True)
        Language.build_library(f'cache/build/typescript.so', [f"cache/tree-sitter-typescript/tsx"])
        subprocess.run(f"cp cache/build/typescript.so /tmp/typescript.so", shell=True)
        self.languages["tsx"] = Language("/tmp/typescript.so", "tsx")

        subprocess.run(f"git clone https://github.com/tree-sitter/tree-sitter-c-sharp cache/tree-sitter-c-sharp",
                       shell=True)
        Language.build_library(f'cache/build/c-sharp.so', [f"cache/tree-sitter-c-sharp"])
        subprocess.run(f"cp cache/build/c-sharp.so /tmp/c-sharp.so", shell=True)
        self.languages["c-sharp"] = Language("/tmp/c-sharp.so", "c_sharp")

        subprocess.run(
            f"git clone https://github.com/tree-sitter/tree-sitter-embedded-template cache/tree-sitter-embedded-template",
            shell=True)
        Language.build_library(f'cache/build/embedded-template.so', [f"cache/tree-sitter-embedded-template"])
        subprocess.run(f"cp cache/build/embedded-template.so /tmp/embedded-template.so", shell=True)
        self.languages["embedded-template"] = Language("/tmp/embedded-template.so", "embedded_template")

        subprocess.run(f"git clone https://github.com/MDeiml/tree-sitter-markdown cache/tree-sitter-markdown",
                       shell=True)
        Language.build_library(f'cache/build/markdown.so', [f"cache/tree-sitter-markdown/tree-sitter-markdown"])
        subprocess.run(f"cp cache/build/markdown.so /tmp/markdown.so", shell=True)
        self.languages["markdown"] = Language("/tmp/markdown.so", "markdown")

        subprocess.run(f"git clone https://github.com/ikatyang/tree-sitter-vue cache/tree-sitter-vue", shell=True)
        Language.build_library(f'cache/build/vue.so', [f"cache/tree-sitter-vue"])
        subprocess.run(f"cp cache/build/vue.so /tmp/vue.so", shell=True)
        self.languages["vue"] = Language("/tmp/vue.so", "vue")

        logger.debug("Finished downloading tree-sitter parsers")

    @method()
    def chunk(
            self,
            file_content: str,
            file_path: str,
            score: float = 1.0,
            additional_metadata: dict[str, str] = {},
            max_chunk_size: int = 512 * 3,
            chunk_size: int = 30,
            overlap: int = 15
    ) -> tuple[list[str], list[dict[str, str]]]:
        """This function returns a list of chunks and a list of metadata for each chunk.
        chunks: list of file chunks
        metadata: list of metadata for each chunk example: {"file_path": "python", "start": 0, "end": 10}
        ids: list of ids for each chunk {file_path}:{start}{end}
        """
        # TODO(Sweep): implement a config file for the above
        # TODO(Sweep): Prioritize the language based on extension
        from tree_sitter import Parser
        file_language = None
        tree = None

        logger.info(f"Chunking {file_path}, size {len(file_content)}")

        _, ext = os.path.splitext(file_path)
        ext = ext[len("."):]
        if ext in extension_to_language:
            # prioritize the language
            language_names = [extension_to_language[ext]]
            language_names += [
                language_name for language_name in self.languages.keys()
                if language_name != extension_to_language[ext]
            ]
            logger.info(language_names)
        else:
            language_names = list(self.languages.keys())

        for language_name in language_names:
            language = self.languages[language_name]
            parser = Parser()
            parser.set_language(language)
            tree = parser.parse(bytes(file_content, "utf-8"))
            if not tree.root_node.children or tree.root_node.children[0].type != "ERROR":
                file_language = language
                break
            logger.warning(f"Not language {language_name}")

        ids = []
        metadatas = []

        if file_language:
            logger.info(file_language.name)
            source_code_bytes = bytes(file_content, "utf-8")
            spans = chunker(tree, source_code_bytes, max_chunk_size)
            ids = [f"{file_path}:{span.start}:{span.end}" for span in spans]
            chunks = [span.extract(file_content) for span in spans]
            for chunk in chunks:
                print(chunk + "\n\n\n")
            for span in spans:
                metadata = {
                    "file_path": file_path,
                    "start": span.start,
                    "end": span.end,
                    "score": score,
                    **additional_metadata
                }
                metadatas.append(metadata)
        else:
            # start and end refers to line here, will fix later
            logger.info("Unknown language")
            source_lines = file_content.split('\n')
            num_lines = len(source_lines)
            logger.info(f"Number of lines: {num_lines}")
            chunks = []
            start_line = 0
            while start_line < num_lines and num_lines > overlap:
                end_line = min(start_line + chunk_size, num_lines)
                chunk = '\n'.join(source_lines[start_line:end_line])
                chunks.append(chunk)
                ids.append(f"{file_path}:{start_line}:{end_line}")
                metadatas.append({
                    "file_path": file_path,
                    "start": start_line,
                    "end": end_line,
                    "score": score,
                    **additional_metadata
                })
                start_line += chunk_size - overlap

        return chunks, metadatas, ids
