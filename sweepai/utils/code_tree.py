import ast
import re
import warnings

import tree_sitter_languages
from pydantic import BaseModel
from tree_sitter import Node, Parser, Tree

warnings.simplefilter("ignore", category=FutureWarning)


class CodeTree(BaseModel):
    code: str
    language: str
    tree: Tree

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_code(cls, code: str, language: str = "python"):
        parser = Parser()
        parser.set_language(tree_sitter_languages.get_language(language))
        tree = parser.parse(bytes(code, "utf8"))
        return cls(code=code, language=language, tree=tree)

    def get_path_to_line(self, min_line: int, max_line: int = -1) -> list[Node]:
        if max_line == -1:
            max_line = min_line
        children: list[Node] = self.tree.root_node.children
        path: list[Node] = [self.tree.root_node]

        while children:
            next_children = []

            for child in children:
                start_line, _ = child.start_point
                end_line, _ = child.end_point
                if start_line <= min_line and max_line <= end_line:
                    path.append(child)
                    next_children.extend(child.children)
                    break

            children = next_children

        start_line, _ = path[-1].start_point
        end_line, _ = path[-1].end_point

        return path

    def get_lines_surrounding(
        self, min_line: int, max_line: int = -1, threshold: int = 4
    ) -> tuple[int, int]:
        if max_line == -1:
            max_line = min_line

        max_num_lines = self.code.count("\n") + 1
        path = self.get_path_to_line(min_line, max_line)
        valid_span = None
        for node in path[::-1]:
            start_line, _ = node.start_point
            end_line, _ = node.end_point
            if (
                0
                < end_line - start_line
                < min(max_line - min_line + threshold, max_num_lines)
            ):
                valid_span = (start_line, end_line)
        if valid_span is not None:
            return valid_span
        else:
            return (min_line, max_line)

    def get_preview(self, min_line: int = 5, max_line: int = -1):
        last_end_line = -1
        lines = self.code.splitlines()
        if max_line == -1:
            # Equation seems to work
            max_line = max(len(lines) // 2 - 200, 50)

        def get_children(node: Node = self.tree.root_node):
            nonlocal last_end_line
            children = []
            for child in node.children:
                start_line, _ = child.start_point
                end_line, _ = child.end_point
                if start_line <= last_end_line:
                    continue
                text = "\n".join(lines[start_line : end_line + 1])
                indentation = " " * (len(text) - len(text.lstrip()))
                for i in range(last_end_line + 1, start_line):
                    line = lines[i]
                    children.append(f"{i} | {line}")
                    last_end_line = i
                if end_line - start_line > max_line:
                    children.extend(get_children(child))
                elif end_line - start_line < min_line:
                    text = "\n".join(
                        [
                            f"{start_line + i} | {line}"
                            for i, line in enumerate(text.split("\n"))
                        ]
                    )
                    children.append(text)
                else:
                    node_lines = text.split("\n")
                    first_line = node_lines[0]
                    first_line = f"{start_line} | {first_line}"
                    second_line = node_lines[1]
                    second_line = f"{start_line + 1} | {second_line}"
                    hidden_lines_content = "\n".join(
                        lines[start_line + 2 : end_line - 1]
                    )
                    number_of_terms = 5
                    first_n_terms = ", ".join(
                        extract_words(hidden_lines_content)[:number_of_terms]
                    )
                    spacing = " " * (len(str(start_line)) + 2)
                    middle_lines = spacing.join(
                        [
                            spacing + indentation + "     ...\n",
                            indentation
                            + f"     (lines {start_line + 1}-{end_line - 1} contains terms: {first_n_terms}\n",
                            indentation + "     ...\n",
                        ]
                    )
                    second_last_line = node_lines[-2]
                    second_last_line = f"{end_line - 1} | {second_last_line}"
                    last_line = node_lines[-1]
                    last_line = f"{end_line} | {last_line}"
                    children.append(first_line)
                    children.append(second_line)
                    children.append(middle_lines)
                    children.append(second_last_line)
                    children.append(last_line)
                last_end_line = end_line
            return children

        return "\n".join(get_children())


def extract_words(string):
    # extract the most common words from a code snippet
    words = re.findall(r"\w+", string)
    return list(dict.fromkeys(words))


def get_global_function_names_and_spans(node):
    return [
        (n.name, (n.lineno, getattr(n, "end_lineno", None)))
        for n in node.body
        if isinstance(n, ast.FunctionDef)
    ]


if __name__ == "__main__":
    snippet = """\
    @patch('os.path.splitext')
    def test_check_comments_presence_with_unsupported_file_extension(self, mock_splitext):
        mock_splitext.return_value = ('file', '.unsupported')
        self.assertEqual(check_comments_presence('file.unsupported', '# This is a comment'), False)"""

    full_code = """\
import unittest
from unittest.mock import patch
from sweepai.utils.comment_utils import check_comments_presence

def helper():
    x = 1
    y = 2
    z = 3
    return x + y + z

class TestCheckCommentsPresence(unittest.TestCase):

    @patch('os.path.splitext')
    def test_check_comments_presence_with_comment(self, mock_splitext):
        mock_splitext.return_value = ('file', '.py')
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        x = 1
        self.assertEqual(check_comments_presence('file.py', '# This is a comment'), True)

    @patch('os.path.splitext')
    def test_check_comments_presence_without_comment(self, mock_splitext):
        mock_splitext.return_value = ('file', '.py')
        self.assertEqual(check_comments_presence('file.py', 'This is not a comment'), False)

    @patch('os.path.splitext')
    def test_check_comments_presence_with_unsupported_file_extension(self, mock_splitext):
        mock_splitext.return_value = ('file', '.unsupported')
        self.assertEqual(check_comments_presence('file.unsupported', '# This is a comment'), False)

    @patch('os.path.splitext')
    def test_check_comments_presence_with_empty_new_code(self, mock_splitext):
        mock_splitext.return_value = ('file', '.py')
        self.assertEqual(check_comments_presence('file.py', ''), False)

if __name__ == '__main__':
    unittest.main()
"""
    # split_code = full_code.split("\n")
    file_contents = open("sweepai/utils/ticket_utils.py").read()
    # file_contents = open("sweepai/handlers/on_ticket.py").read()
    # file_contents = full_code
    # match_start = 16
    # match_end = 20
    code_tree = CodeTree.from_code(file_contents)
    print(code_tree.get_preview())
    print(len(code_tree.get_preview().split("\n")))
    # print(code_tree.get_lines_surrounding(match_start)[0])
    # print(code_tree.get_lines_surrounding(match_end)[1])