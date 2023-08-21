import modal
from loguru import logger

from sweepai.config.env import DOCS_MODAL_INST_NAME
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.prompts import docs_qa_system_prompt, docs_qa_user_prompt
from sweepai.pre_indexed_docs import DOCS_ENDPOINTS


class DocumentationSearcher(ChatGPT):
    # Mostly copied from external_searcher.py
    # TODO: refactor to avoid code duplication
    # no but seriously, refactor this

    @staticmethod
    def extract_docs_links(content: str, user_dict: dict) -> list[str]:
        urls = []
        logger.info(content)
        # add the user_dict to DOC_ENDPOINTS
        assert isinstance(user_dict, dict), "user_dict must be a dict"
        if user_dict:
            DOCS_ENDPOINTS.update(user_dict)
        for framework, url in DOCS_ENDPOINTS.items():
            if (
                framework.lower() in content.lower()
                or framework.lower().replace(" ", "") in content.lower()
            ):
                urls.append(url)
        return urls

    def extract_resources(self, url: str, problem: str) -> str:
        # MVP
        docs_search = modal.Function.lookup(DOCS_MODAL_INST_NAME, "search_vector_store")
        results = docs_search.call(url, problem)

        metadatas = results["metadata"]
        docs = results["text"]

        new_metadatas = []
        new_docs = []

        for metadata, doc in zip(metadatas, docs):
            if metadata not in new_metadatas:
                new_metadatas.append(metadata)
                new_docs.append(doc)

        self.messages = [
            Message(
                role="system",
                content=docs_qa_system_prompt,
            ),
        ]
        answer = self.chat(
            docs_qa_user_prompt.format(
                snippets="\n\n".join(
                    [
                        f"**{metadata['url']}:**\n\n{doc}"
                        for metadata, doc in zip(new_metadatas, new_docs)
                    ]
                ),
                problem=problem,
            ),
        )
        return (
            f"**Summary of related docs from {url}:**\n\n{answer}\n\nSources:\n"
            + "\n\n".join([f"* {metadata['url']}" for metadata in new_metadatas])
        )

    @staticmethod
    def extract_relevant_docs(content: str, user_dict: dict):
        logger.info("Fetching related APIs from content")
        links = DocumentationSearcher.extract_docs_links(content, user_dict)
        if not links:
            return ""
        result = "\n\n### I also found some related docs:\n\n"
        logger.info("Extracting docs from links")
        for link in links:
            logger.info(f"Fetching docs summary from {link}")
            try:
                external_searcher = DocumentationSearcher()
                summary = external_searcher.extract_resources(link, content)
                result += "> " + summary.replace("\n", "\n> ") + "\n\n"
            except Exception as e:
                logger.error(f"Docs search error: {e}")
        return result
