import os

import openai
from llama_index import GPTVectorStoreIndex, download_loader

openai.api_key = os.environ.get("OPENAI_API_KEY")

SimpleWebPageReader = download_loader("SimpleWebPageReader")
loader = SimpleWebPageReader()
url = "https://modal.com/docs/guide/continuous-deployment#github-actions"
documents = loader.load_data(urls=[url])
document = documents[0]

index = GPTVectorStoreIndex.from_documents(documents)
query_engine = index.as_query_engine(streaming=True)
query_engine.query(
    "Extract the entire example yaml from the html."
).print_response_stream()
