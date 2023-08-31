import shutil
import traceback
from dataclasses import dataclass
import itertools
import re
from whoosh.analysis import Tokenizer, Token
import os
import random
import time

random.seed(os.getpid())


class CodeTokenizer(Tokenizer):
    def __init__(self, top_words=None):
        self.top_words = top_words

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
        **kwargs,
    ):
        pos = start_pos
        for match in re.finditer(r"\w+(?:\w+)*", value):
            t_text = match.group()
            if not self.top_words or t_text.lower() not in self.top_words:
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
                        if not self.top_words or part.lower() not in self.top_words:
                            yield Token(
                                text=part.lower(),
                                pos=pos,
                                start_char=match.start(),
                                end_pos=pos + 1,
                                end_char=match.end(),
                            )

            # Handle PascalCase and camelCase
            if re.search(r"[A-Z][a-z]|[a-z][A-Z]|[0-9]", t_text):
                parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", t_text)
                for part in parts:
                    if len(part) > 1:  # And here
                        pos += 1
                        if not self.top_words or part.lower() not in self.top_words:
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
    start: int
    end: int


def snippets_to_docs(snippets):
    docs = []
    for snippet in snippets:
        docs.append(
            Document(
                title=snippet.file_path[len("repo/") :],
                content=snippet.content,
                start=snippet.start,
                end=snippet.end,
            )
        )
    return docs


from whoosh.qparser import QueryParser, OrGroup
import os
from whoosh import index
from whoosh.fields import Schema, TEXT, NUMERIC


def get_stopwords(snippets):
    from collections import Counter

    # Assuming your CodeTokenizer is defined and works for your specific content
    tokenizer = CodeTokenizer()

    # Let's say your content is in a variable called "content"
    chunks = [snippet.content for snippet in snippets]
    tokens = [t.text for t in tokenizer("\n".join(chunks))]
    # Count the frequency of each word
    word_counts = Counter(tokens)

    # Identify the top 100 most frequent words
    top_words = {word for word, _ in word_counts.most_common(25)}
    return top_words


def prepare_index_from_snippets(snippets):
    all_docs = snippets_to_docs(snippets)
    # Tokenizer that splits by whitespace and common code punctuation
    stop_words = get_stopwords(snippets)
    tokenizer = CodeTokenizer(stop_words)

    # An example analyzer for code
    code_analyzer = tokenizer

    schema = Schema(
        title=TEXT(stored=True, analyzer=code_analyzer),
        content=TEXT(stored=True, analyzer=code_analyzer),
        start=NUMERIC(stored=True),
        end=NUMERIC(stored=True),
    )

    # Create a directory to store the index
    pid = random.randint(0, 100)
    shutil.rmtree(f"cache/indexdir_{pid}", ignore_errors=True)
    os.mkdir(f"cache/indexdir_{pid}")

    # Create the index based on the schema
    ix = index.create_in(f"cache/indexdir_{pid}", schema)
    # writer.cancel()
    writer = ix.writer()
    for doc in all_docs:
        writer.add_document(title=doc.title, content=doc.content)

    writer.commit()
    return ix


@dataclass
class Documentation:
    url: str
    content: str


def prepare_index_from_docs(docs):
    all_docs = [Documentation(url, content) for url, content in docs]
    tokenizer = CodeTokenizer()
    # An example analyzer for code
    code_analyzer = tokenizer

    schema = Schema(
        url=TEXT(stored=True, analyzer=code_analyzer),
        content=TEXT(stored=True, analyzer=code_analyzer),
    )

    # Create a directory to store the index
    pid = random.randint(0, 100)
    if not os.path.exists(f"indexdir_{pid}"):
        os.mkdir(f"indexdir_{pid}")

    # Create the index based on the schema
    ix = index.create_in("indexdir_{pid}", schema)
    # writer.cancel()
    writer = ix.writer()
    for doc in all_docs:
        writer.add_document(url=doc.url, content=doc.content)

    writer.commit()
    return ix


def search_docs(query, ix):
    """Title, score, content"""
    # Create a query parser for the "content" field of the index
    qp = QueryParser("content", schema=ix.schema, group=OrGroup)
    q = qp.parse(query)

    # Search the index
    with ix.searcher() as searcher:
        results = searcher.search(q, limit=None, terms=True)
        # return dictionary of content to scores
        res = {}
        for hit in results:
            if hit["url"] not in res:
                res[hit["url"]] = hit.score
            else:
                res[hit["url"]] = max(hit.score, res[hit["url"]])
        # min max normalize scores from 0.5 to 1
        max_score = max(res.values())
        min_score = min(res.values()) if min(res.values()) < max_score else 0
        return {k: (v - min_score) / (max_score - min_score) for k, v in res.items()}


def search_index(query, ix):
    """Title, score, content"""
    # Create a query parser for the "content" field of the index
    qp = QueryParser("content", schema=ix.schema, group=OrGroup)
    q = qp.parse(query)

    # Search the index
    with ix.searcher() as searcher:
        results = searcher.search(q, limit=None, terms=True)
        # return dictionary of content to scores
        res = {}
        for hit in results:
            if hit["title"] not in res:
                res[hit["title"]] = hit.score
            else:
                res[hit["title"]] = max(hit.score, res[hit["title"]])
        # min max normalize scores from 0.5 to 1
        if len(res) == 0:
            max_score = 1
            min_score = 0
        else:
            max_score = max(res.values())
            min_score = min(res.values()) if min(res.values()) < max_score else 0
        return {k: (v - min_score) / (max_score - min_score) for k, v in res.items()}
