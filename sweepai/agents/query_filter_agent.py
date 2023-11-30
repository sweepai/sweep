import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT


class QueryFilterBot(ChatGPT):
    """
    A bot that filters unnecessary terms out of a search query.
    """
    prompt = """\
    <search_query>
    {search_query}
    </search_query>
    Filter out unnecessary terms from the above search query.
    <filtered_query>
    {filtered_query}
    </filtered_query>
    """

    def __init__(self, chat_logger=None):
        """
        Initialize the bot with a model based on the user's status.
        """
        super().__init__(chat_logger)
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )

    def filter_query(self, search_query):
        """
        Filter out unnecessary terms from the search query.
        """
        response = self.chat(
            content=self.prompt.format(search_query=search_query)
        )
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response):
        """
        Parse the response to extract the filtered query.
        """
        pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        match = re.search(pattern, response, re.DOTALL)
        return match.group(1).strip() if match else None
