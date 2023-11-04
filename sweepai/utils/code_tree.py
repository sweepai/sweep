import ast

import tree_sitter_languages
from pydantic import BaseModel
from tree_sitter import Node, Parser, Tree


class CodeTree(BaseModel):
    code: str
    tree: Tree

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_code(cls, code: str):
        parser = Parser()
        parser.set_language(tree_sitter_languages.get_language("python"))
        tree = parser.parse(bytes(code, "utf8"))
        return cls(code=code, tree=tree)

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

class TestCheckCommentsPresence(unittest.TestCase):

    @patch('os.path.splitext')
    def test_check_comments_presence_with_comment(self, mock_splitext):
        mock_splitext.return_value = ('file', '.py')
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
    split_code = full_code.split("\n")
    match_start = 16
    match_end = 20
    code_tree = CodeTree.from_code(full_code)
    print(code_tree.get_lines_surrounding(match_start)[0])
    print(code_tree.get_lines_surrounding(match_end)[1])
