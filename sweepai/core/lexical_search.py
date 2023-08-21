from dataclasses import dataclass
import itertools
import re
from whoosh.analysis import Tokenizer, Token

from sweepai.utils.utils import chunk_code


class CodeTokenizer(Tokenizer):
    def __call__(
        self,
        value,
        positions=False,
        chars=False,
        keeporiginal=False,
        removestops=True,
        start_pos=0,
        start_char=0,
        mode="",
        **kwargs
    ):
        pos = start_pos
        for match in re.finditer(r"\w+(?:_\w+)*", value):
            t_text = match.group()
            if len(t_text) > 1:  # Add this condition to filter out tokens with length 1
                yield Token(
                    text=t_text.lower(),
                    pos=pos,
                    start_char=match.start(),
                    end_pos=pos + 1,
                    end_char=match.end(),
                )

                # Handle snake_case
                if "_" in t_text:
                    for part in t_text.split("_"):
                        if len(part) > 1:  # Same condition here
                            pos += 1
                            yield Token(
                                text=part.lower(),
                                pos=pos,
                                start_char=match.start(),
                                end_pos=pos + 1,
                                end_char=match.end(),
                            )

                # Handle PascalCase and camelCase
                if re.search(r"[A-Z][a-z]|[a-z][A-Z]", t_text):
                    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", t_text)
                    for part in parts:
                        if len(part) > 1:  # And here
                            pos += 1
                            yield Token(
                                text=part.lower(),
                                pos=pos,
                                start_char=match.start(),
                                end_pos=pos + 1,
                                end_char=match.end(),
                            )

            pos += 1


@dataclass
class Document:
    title: str
    content: str
    path: str
