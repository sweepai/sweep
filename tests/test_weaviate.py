import modal
from sweepai.utils.config.server import DOCS_MODAL_INST_NAME


import modal 
stub = modal.Stub(DOCS_MODAL_INST_NAME)
doc_url = "https://docs.anthropic.com/claude"
search = modal.Function.lookup(DOCS_MODAL_INST_NAME, "search_vector_store")
write = modal.Function.lookup(DOCS_MODAL_INST_NAME, "write_documentation")
print(write.call(doc_url))
print(search.call(doc_url, "how do i use the claude api"))