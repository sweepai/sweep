import os
import random
import re
import traceback
from dataclasses import dataclass

from whoosh.analysis import Token, Tokenizer
from whoosh.filedb.filestore import RamStorage
from whoosh.query import Or, Term

from logn import logger
from sweepai.core.entities import Snippet

random.seed(os.getpid())


def tokenize_call(code):
    def check_valid_token(token):
        return token and len(token) > 1

    matches = re.finditer(r"\b\w+\b", code)
    pos = 0
    valid_tokens = []
    for m in matches:
        text = m.group()
        span_start = m.start()
        span_end = m.end()

        if "_" in text:  # snakecase
            offset = 0
            for part in text.split("_"):
                if check_valid_token(part):
                    valid_tokens.append(
                        Token(
                            text=part.lower(),
                            pos=pos,
                            startchar=span_start + offset,
                            end_pos=pos + 1,
                            endchar=span_start + len(part) + offset,
                        )
                    )
                    pos += 1
                offset += len(part) + 1
        elif re.search(r"[A-Z][a-z]|[a-z][A-Z]", text):  # pascal and camelcase
            parts = re.findall(
                r"([A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z]|$))", text
            )  # first one "MyVariable" second one "myVariable" third one "MYVariable"
            offset = 0
            for part in parts:
                if check_valid_token(part):
                    valid_tokens.append(
                        Token(
                            text=part.lower(),
                            pos=pos,
                            startchar=span_start + offset,
                            end_pos=pos + 1,
                            endchar=span_start + len(part) + offset,
                        )
                    )
                    pos += 1
                offset += len(part)
        else:  # everything else
            if check_valid_token(text):
                valid_tokens.append(
                    Token(
                        text=text.lower(),
                        pos=pos,
                        startchar=span_start,
                        end_pos=pos + 1,
                        endchar=span_start + len(text),
                    )
                )
                pos += 1
    return valid_tokens


def construct_query(query):
    terms = tokenize_call(query)
    bigrams = construct_bigrams(terms)
    trigrams = construct_trigrams(terms)
    terms.extend(bigrams)
    terms.extend(trigrams)
    return Or([Term("content", term.text) for term in terms])


def construct_bigrams(tokens):
    res = []
    prev_token = None
    for token in tokens:
        if prev_token:
            joined_token = Token(
                text=prev_token.text + "_" + token.text,
                pos=prev_token.pos,
                startchar=prev_token.startchar,
                end_pos=token.end_pos,
                endchar=token.endchar,
            )
            res.append(joined_token)
        prev_token = token
    return res


def construct_trigrams(tokens):
    res = []
    prev_prev_token = None
    prev_token = None
    for token in tokens:
        if prev_token and prev_prev_token:
            joined_token = Token(
                text=prev_prev_token.text + "_" + prev_token.text + "_" + token.text,
                pos=prev_prev_token.pos,
                startchar=prev_prev_token.startchar,
                end_pos=token.end_pos,
                endchar=token.endchar,
            )
            res.append(joined_token)
        prev_prev_token = prev_token
        prev_token = token
    return res


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
        **kwargs,
    ):
        tokens = tokenize_call(value)
        bigrams = construct_bigrams(tokens)
        trigrams = construct_trigrams(tokens)
        tokens.extend(bigrams)
        tokens.extend(trigrams)
        for token in tokens:
            yield token


@dataclass
class Document:
    title: str
    content: str
    start: int
    end: int


def snippets_to_docs(snippets: list[Snippet], len_repo_cache_dir):
    from tqdm import tqdm

    docs = []
    for snippet in tqdm(snippets):
        docs.append(
            Document(
                title=snippet.file_path[len_repo_cache_dir:],
                content=snippet.get_snippet(add_ellipsis=False, add_lines=False),
                start=snippet.start,
                end=snippet.end,
            )
        )
    return docs


import os

from whoosh.fields import NUMERIC, TEXT, Schema


def prepare_index_from_snippets(snippets, len_repo_cache_dir=0):
    from tqdm import tqdm

    all_docs = snippets_to_docs(snippets, len_repo_cache_dir)
    # Tokenizer that splits by whitespace and common code punctuation
    tokenizer = CodeTokenizer()

    # An example analyzer for code
    code_analyzer = tokenizer

    schema = Schema(
        title=TEXT(stored=True, analyzer=code_analyzer),
        content=TEXT(stored=True, analyzer=code_analyzer),
        start=NUMERIC(stored=True),
        end=NUMERIC(stored=True),
    )

    # Create the index based on the schema
    storage = RamStorage()
    ix = storage.create_index(schema)
    writer = ix.writer()
    for doc in tqdm(all_docs, total=len(all_docs)):
        writer.add_document(
            title=doc.title, content=doc.content, start=doc.start, end=doc.end
        )

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

    storage = RamStorage()
    ix = storage.create_index(schema)
    writer = ix.writer()
    for doc in all_docs:
        writer.add_document(url=doc.url, content=doc.content)

    try:
        writer.commit()
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(e)
    return ix


def search_docs(query, ix):
    """Title, score, content"""
    # Create a query parser for the "content" field of the index
    q = construct_query(query)

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
        res = {k: (v - min_score) / (max_score - min_score) for k, v in res.items()}
    ix.writer().cancel()
    return res


def search_index(query, ix):
    """Title, score, content"""
    try:
        # Create a query parser for the "content" field of the index
        q = construct_query(query)

        # Search the index
        with ix.searcher() as searcher:
            results = searcher.search(q, limit=None, terms=True)
            # return dictionary of content to scores
            res = {}
            for hit in results:
                key = f"{hit['title']}:{str(hit['start'])}:{str(hit['end'])}"
                if key not in res:
                    res[key] = hit.score
            # min max normalize scores from 0.5 to 1
            if len(res) == 0:
                max_score = 1
                min_score = 0
            else:
                max_score = max(res.values())
                min_score = min(res.values()) if min(res.values()) < max_score else 0
            res = {k: (v - min_score) / (max_score - min_score) for k, v in res.items()}
        ix.writer().cancel()
        return res
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.print(e)
        traceback.print_exc()
        return {}
