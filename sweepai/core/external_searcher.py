import re

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.prompts import external_search_prompt, external_search_system_prompt
from loguru import logger
from sweepai.utils.html_extractor import extract_info


class ExternalSearcher(ChatGPT):
    @staticmethod
    def extract_links(content: str) -> list[str]:
        pattern = r"\b(?:(?:https?|ftp)://|www\.)\S+\b"
        return list(set(re.findall(pattern, content)))

    def extract_summary_from_link(self, url: str, problem: str) -> str:
        page_metadata = extract_info(url)

        self.messages = [Message(role="system", content=external_search_system_prompt)]
        response = self.chat(
            external_search_prompt.format(
                page_metadata=page_metadata,
                problem=problem,
            )
        )

        return response.strip() + "\n"

    @staticmethod
    def extract_summaries(content: str):
        logger.info("Extracting summaries from content")
        links = ExternalSearcher.extract_links(content)
        if not links:
            return ""
        result = "\n\n**Summaries of links found in the content:**\n\n"
        for link in links:
            logger.info(f"Extracting summary from {link}")
            try:
                external_searcher = ExternalSearcher()
                summary = external_searcher.extract_summary_from_link(link, content)
                result += f"{link}:\n\n{summary}\n\n"
            except Exception as e:
                logger.error(f"External search error: {e}")
        return result
