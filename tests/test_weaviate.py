from sweepai.config.server import DOCS_MODAL_INST_NAME


import modal

from sweepai.core.lexical_search import prepare_index_from_docs, search_docs

stub = modal.Stub(DOCS_MODAL_INST_NAME)
# doc_url = "https://docs.anthropic.com/claude"
doc_url = "https://particles.js.org/docs"
update = modal.Function.lookup(DOCS_MODAL_INST_NAME, "daily_update")
search = modal.Function.lookup(DOCS_MODAL_INST_NAME, "search_vector_store")
write = modal.Function.lookup(DOCS_MODAL_INST_NAME, "write_documentation")
# print(write.call(doc_url))
results = search.call(doc_url, "How do I add random particles?")
metadatas = results["metadata"]
docs = results["text"]
vector_scores = results["score"]
url_and_docs = [(metadata["url"], doc) for metadata, doc in zip(metadatas, docs)]
ix = prepare_index_from_docs(url_and_docs)
docs_to_scores = search_docs("test", ix)
import pdb

pdb.set_trace()
for idx, (url, doc) in enumerate(url_and_docs):
    print(doc, docs_to_scores[url], vector_scores[idx] + "========\n")
# new_docs = []
# for doc in docs:
#     if doc not in new_docs:
#         new_docs.append(doc)
# new_docs = new_docs[:min(5, len(new_docs))]
# for doc in new_docs:
#     print(doc + "\n\n\n")
# update.call()
