from sweepai.core.chat import ChatGPT


class QueryFilterAgent(ChatGPT):
    def filter_search_query(self, search_query: str, title: str, summary: str, replies_text: str) -> str:
        prompt = f"""\
        This is the issue:
        Title: {title}
        Summary: {summary}
        Replies: {replies_text}
        Current search query: {search_query}
        
        Please filter out unnecessary terms from the search query to improve the effectiveness of a lexical search.
        """

        response = self.chat(content=prompt)
        # Assuming the AI response contains the filtered query in a specific format, e.g., "Filtered query: <query>"
        filtered_query = response.split("Filtered query: ")[-1].strip()
        return filtered_query
