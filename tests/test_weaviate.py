import modal
from sweepai.utils.config.server import DOCS_MODAL_INST_NAME


import modal 
stub = modal.Stub(DOCS_MODAL_INST_NAME)
# doc_url = "https://docs.anthropic.com/claude"
doc_url = "https://docs.anthropic.com/claude/docs"
update = modal.Function.lookup(DOCS_MODAL_INST_NAME, "daily_update")
search = modal.Function.lookup(DOCS_MODAL_INST_NAME, "search_vector_store")
write = modal.Function.lookup(DOCS_MODAL_INST_NAME, "write_documentation")
# print(write.call(doc_url))
results = search.call(doc_url, "how do i use the claude api")
metadatas = results["metadata"]
docs = results["text"]
print(docs)
# new_docs = []
# for doc in docs:
#     if doc not in new_docs:
#         new_docs.append(doc)
# new_docs = new_docs[:min(5, len(new_docs))]
# for doc in new_docs:
#     print(doc + "\n\n\n")
# update.call()