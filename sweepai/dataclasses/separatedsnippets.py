from dataclasses import dataclass, field
from typing import Iterator, Tuple
from sweepai.core.entities import Snippet

@dataclass
class SeparatedSnippets:
    tools: list[Snippet] = field(default_factory=list)
    junk: list[Snippet] = field(default_factory=list)
    dependencies: list[Snippet] = field(default_factory=list)
    docs: list[Snippet] = field(default_factory=list)
    tests: list[Snippet] = field(default_factory=list)
    source: list[Snippet] = field(default_factory=list)

    def add_snippet(self, snippet: Snippet, type_name: str):
        if type_name == "tools":
            self.tools.append(snippet)
        elif type_name == "junk":
            self.junk.append(snippet)
        elif type_name == "dependencies":
            self.dependencies.append(snippet)
        elif type_name == "docs":
            self.docs.append(snippet)
        elif type_name == "tests":
            self.tests.append(snippet)
        elif type_name == "source":
            self.source.append(snippet)
        else:
            raise ValueError(f"Unknown type_name: {type_name}")
    
    def override_list(self, attribute_name: str, new_list: list[Snippet]):
        if hasattr(self, attribute_name):
            setattr(self, attribute_name, new_list)
        else:
            raise AttributeError(f"List type '{attribute_name}' does not exist in SeparatedSnippets")

    def __iter__(self) -> Iterator[Tuple[str, list[Snippet]]]:
        yield "source", self.source
        yield "tests", self.tests
        yield "tools", self.tools
        yield "dependencies", self.dependencies
        yield "docs", self.docs
        # yield "junk", self.junk
        # we won't yield junk