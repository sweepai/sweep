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
        self, min_line: int, max_line: int = -1, threshold: int = 20
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
