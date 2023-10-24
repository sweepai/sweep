import re
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import log

from tqdm import tqdm
from whoosh.analysis import Token, Tokenizer

from sweepai.core.entities import Snippet
from sweepai.logn import logger


class CustomIndex:
    def __init__(self):
        self.inverted_index = defaultdict(list)
        self.doc_lengths = {}
        self.avg_doc_length = 0.0
        self.k1 = 1.2
        self.b = 0.75
        self.metadata = {}  # Store custom metadata here
        self.tokenizer = CodeTokenizer()

    def add_document(self, title, content, metadata={}):
        doc_id = title  # You can use title as doc_id or make it more unique
        self.metadata[doc_id] = metadata
        self.index_document(doc_id, title + content)

    def index_document(self, doc_id, content):
        tokens = [token.text for token in self.tokenizer(content)]
        doc_length = len(tokens)
        self.doc_lengths[doc_id] = doc_length
        self.avg_doc_length = sum(self.doc_lengths.values()) / len(self.doc_lengths)

        token_freq = Counter(tokens)
        for token, freq in token_freq.items():
            self.inverted_index[token].append((doc_id, freq))

    def bm25(self, doc_id, term, term_freq):
        num_docs = len(self.doc_lengths)
        idf = log(
            ((num_docs - len(self.inverted_index[term])) + 0.5)
            / (len(self.inverted_index[term]) + 0.5)
            + 1.0
        )
        doc_length = self.doc_lengths[doc_id]
        tf = ((self.k1 + 1) * term_freq) / (
            term_freq
            + self.k1 * (1 - self.b + self.b * (doc_length / self.avg_doc_length))
        )
        return idf * tf

    def search_index(self, query):
        query_tokens = [token.text for token in self.tokenizer(query)]
        scores = defaultdict(float)

        for token in query_tokens:
            for doc_id, term_freq in self.inverted_index.get(token, []):
                scores[doc_id] += self.bm25(doc_id, token, term_freq)

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Attach metadata to the results
        results_with_metadata = [
            (doc_id, score, self.metadata.get(doc_id, {}))
            for doc_id, score in sorted_scores
        ]

        return results_with_metadata


def tokenize_call(code):
    def check_valid_token(token):
        return token and len(token) > 1

    matches = re.finditer(r"\b\w+\b", code)
    pos = 0
    valid_tokens = []
    for m in matches:
        text = m.group()
        span_start = m.start()

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


def prepare_index_from_snippets(snippets, len_repo_cache_dir=0):
    all_docs = snippets_to_docs(snippets, len_repo_cache_dir)
    if len(all_docs) == 0:
        return None
    # Create the index based on the schema
    index = CustomIndex()
    try:
        for doc in tqdm(all_docs, total=len(all_docs)):
            index.add_document(
                title=f"{doc.title}:{doc.start}:{doc.end}", content=doc.content
            )
    except FileNotFoundError as e:
        logger.error(e)

    return index


@dataclass
class Documentation:
    url: str
    content: str


def prepare_index_from_docs(docs):
    all_docs = [Documentation(url, content) for url, content in docs]
    if len(all_docs) == 0:
        return None
    # Create the index based on the schema
    index = CustomIndex()
    try:
        for doc in tqdm(all_docs, total=len(all_docs)):
            index.add_document(title=f"{doc.url}", content=doc.content)
    except FileNotFoundError as e:
        logger.error(e)
    return index


def search_docs(query, index: CustomIndex):
    """Title, score, content"""
    if index == None:
        return {}
    results_with_metadata = index.search_index(query)
    # Search the index
    res = {}
    for doc_id, score, _ in results_with_metadata:
        if doc_id not in res:
            res[doc_id] = score
    # min max normalize scores from 0.5 to 1
    if len(res) == 0:
        max_score = 1
        min_score = 0
    else:
        max_score = max(res.values())
        min_score = min(res.values()) if min(res.values()) < max_score else 0
    res = {k: (v - min_score) / (max_score - min_score) for k, v in res.items()}
    return res


def search_index(query, index: CustomIndex):
    """Title, score, content"""
    if index == None:
        return {}
    try:
        # Create a query parser for the "content" field of the index
        results_with_metadata = index.search_index(query)
        # Search the index
        res = {}
        for doc_id, score, _ in results_with_metadata:
            if doc_id not in res:
                res[doc_id] = score
        # min max normalize scores from 0.5 to 1
        if len(res) == 0:
            max_score = 1
            min_score = 0
        else:
            max_score = max(res.values())
            min_score = min(res.values()) if min(res.values()) < max_score else 0
        res = {k: (v - min_score) / (max_score - min_score) for k, v in res.items()}
        return res
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.print(e)
        traceback.print_exc()
        return {}
