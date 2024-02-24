from sweepai.core.prompts import doc_query_rewriter_prompt
from sweepai.utils.openai_proxy import OpenAIProxy
from sweepai.watch import logger


class QueryFilterAgent:
    def __init__(self):
        self.openai_proxy = OpenAIProxy()

    def filter_query(self, search_query: str) -> str:
        try:
            prompt = doc_query_rewriter_prompt.format(issue=search_query)
            filtered_query = self.openai_proxy.call_openai(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": prompt}],
                max_tokens=60,
                temperature=0.0
            )
            return filtered_query
        except Exception as e:
            logger.error(f"Error filtering query: {e}")
            raise e
