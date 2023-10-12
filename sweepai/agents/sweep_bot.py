from loguru import logger
from sweepai.agents.extract_leftover_comments import ExtractLeftoverComments

class SweepBot:
    def __init__(self):
        self.extract_leftover_comments_bot = ExtractLeftoverComments()

    def fuse_matches(self, snippets: list) -> list:
        if len(snippets) > 3:
            snippets = sorted(snippets, key=lambda x: len(x), reverse=True)[:3]
        return snippets

    def handle_exception(self, e: Exception):
        logger.exception(f"An error occurred: {e}")
