from sweepai.config.server import DOCS_MODAL_INST_NAME


import modal 
stub = modal.Stub(DOCS_MODAL_INST_NAME)
# doc_url = "https://docs.anthropic.com/claude"
doc_url = "https://particles.js.org/docs"
update = modal.Function.lookup(DOCS_MODAL_INST_NAME, "daily_update")
search = modal.Function.lookup(DOCS_MODAL_INST_NAME, "search_vector_store")
write = modal.Function.lookup(DOCS_MODAL_INST_NAME, "write_documentation")
print(write.call(doc_url))
results = search.call(doc_url, "Where are the config files stored")
metadatas = results["metadata"]
docs = results["text"]
print(docs[0])
import pdb; pdb.set_trace()
# new_docs = []
# for doc in docs:
#     if doc not in new_docs:
#         new_docs.append(doc)
# new_docs = new_docs[:min(5, len(new_docs))]
# for doc in new_docs:
#     print(doc + "\n\n\n")
# update.call()