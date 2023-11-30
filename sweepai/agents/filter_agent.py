import re

from sweepai.core.chat import ChatGPT


class FilterBot(ChatGPT):
    def filter_query(self, query):
        # Remove non-alphanumeric characters
        query = re.sub(r'\W+', ' ', query)
        
        # Split the query into individual words
        words = query.split()
        
        # Define a list of common stop words to filter out
        stop_words = ['the', 'is', 'at', 'which', 'on']
        
        # Filter out the stop words
        filtered_words = [word for word in words if word not in stop_words]
        
        # Return the filtered query as a string
        return ' '.join(filtered_words)
