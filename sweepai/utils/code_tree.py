import ast

from pydantic import BaseModel


class CodeTree(BaseModel):
    code: str
    syntax_tree: ast.AST

    @classmethod
    def from_code(cls, code: str):
        return cls(code=code, syntax_tree=ast.parse(code))

    def get_entities(self):
        return self.syntax_tree.body
