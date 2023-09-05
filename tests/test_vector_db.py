import os
from sweepai.core.vector_db import embed_texts

# Define a list of texts for testing
texts = ["This is a test text.", "Another test text."]

# Set the HUGGINGFACE_URL and HUGGINGFACE_TOKEN environment variables
os.environ["HUGGINGFACE_URL"] = "https://api.huggingface.co"
os.environ["HUGGINGFACE_TOKEN"] = "your_token_here"

# Call the embed_texts function with the list of texts
result = embed_texts(texts)

# Print the result
print(result)
