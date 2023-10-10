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

    # def get_branches(self, min_lines: int = 20):
    #     current_

    def get_path_to_line(self, line_number) -> list[Node]:
        children: list[Node] = self.tree.root_node.children
        path: list[Node] = [self.tree.root_node]

        while children:
            next_children = []

            for child in children:
                start_line, _ = child.start_point
                end_line, _ = child.end_point
                if start_line <= line_number <= end_line:
                    path.append(child)
                    next_children.extend(child.children)
                    break

            children = next_children

        start_line, _ = path[-1].start_point
        end_line, _ = path[-1].end_point

        return path

    def get_lines_surrounding(
        self, line_number, threshold: int = 20
    ) -> tuple[int, int]:
        max_lines = self.code.count("\n") + 1
        path = self.get_path_to_line(line_number)
        for node in path[::-1]:
            start_line, _ = node.start_point
            end_line, _ = node.end_point
            if 0 < end_line - start_line < min(threshold, max_lines):
                return (start_line, end_line)
        return (line_number, line_number)
