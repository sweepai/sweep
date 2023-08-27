import modal
from loguru import logger
from sweepai.config.server import DOCS_MODAL_INST_NAME

from sweepai.core.chat import ChatGPT
from sweepai.core.documentation import DOCS_ENDPOINTS
from sweepai.core.entities import Message
from sweepai.core.prompts import docs_qa_system_prompt, docs_qa_user_prompt

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.prompts import (
    doc_query_rewriter_system_prompt,
    doc_query_rewriter_prompt,
)
from sweepai.utils.chat_logger import ChatLogger

DOCS_ENDPOINTS = DOCS_ENDPOINTS


class DocQueryRewriter(ChatGPT):
    # rewrite the query to be more relevant to the docs
    def rewrite_query(self, package: str, description: str, issue: str) -> str:
        self.messages = [
            Message(
                role="system",
                content=doc_query_rewriter_system_prompt.format(
                    package=package, description=description
                ),
            )
        ]
        self.model = "gpt-3.5-turbo-16k-0613"  # can be optimized
        response = self.chat(doc_query_rewriter_prompt.format(issue=issue))
        self.undo()
        return response.strip() + "\n"


def extract_docs_links(content: str, user_dict: dict) -> list[str]:
    urls = []
    logger.info(content)
    # add the user_dict to DOC_ENDPOINTS
    assert isinstance(user_dict, dict), "user_dict must be a dict"
    if user_dict:
        DOCS_ENDPOINTS.update(user_dict)
    for framework, (url, _) in DOCS_ENDPOINTS.items():
        if (
            framework.lower() in content.lower()
            or framework.lower().replace(" ", "") in content.lower()
        ):
            urls.append(url)
    return urls


class DocumentationSearcher(ChatGPT):
    # Mostly copied from external_searcher.py
    # TODO: refactor to avoid code duplication
    # no but seriously, refactor this

    def extract_resources(
        self, url: str, content: str, user_dict: dict, chat_logger: ChatLogger
    ) -> str:
        # MVP
        docs_search = modal.Function.lookup(DOCS_MODAL_INST_NAME, "search_vector_store")
        description = ""
        package = ""
        for framework, (package_url, description) in DOCS_ENDPOINTS.items():
            if package_url == url:
                package = framework
                description = description
                break
        rewritten_problem = DocQueryRewriter(
            chat_logger=chat_logger, model="gpt-3.5-turbo-16k-0613"
        ).rewrite_query(package=package, description=description, issue=content)
        urls, docs = docs_search.call(url, rewritten_problem)

        self.messages = [
            Message(
                role="system",
                content=docs_qa_system_prompt,
            ),
        ]
        answer = self.chat(
            docs_qa_user_prompt.format(
                snippets="\n\n".join(
                    [f"**{url}:**\n\n{doc}" for url, doc in zip(urls, docs)]
                ),
                problem=content,
            ),
        )
        return (
            f"**Summary of related docs from {url}:**\n\n{answer}\n\nSources:\n"
            + "\n\n".join([f"* {url}" for url in urls])
        )


def extract_relevant_docs(content: str, user_dict: dict, chat_logger: ChatLogger):
    links = extract_docs_links(content, user_dict)
    if not links:
        return ""
    result = "\n\n### I also found some related docs:\n\n"
    for link in links:
        logger.info(f"Fetching docs summary from {link}")
        try:
            external_searcher = DocumentationSearcher(
                chat_logger=chat_logger, model="gpt-3.5-turbo-16k-0613"
            )
            summary = external_searcher.extract_resources(
                link, content, user_dict, chat_logger
            )
            result += "> " + summary.replace("\n", "\n> ") + "\n\n"
        except Exception as e:
            logger.error(f"Docs search error: {e}")
    return result
