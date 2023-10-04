import modal

from sweepai.config.server import DOCS_MODAL_INST_NAME

stub = modal.Stub(DOCS_MODAL_INST_NAME)
# doc_url = "https://docs.anthropic.com/claude"
doc_url = "https://modal.com/docs/guide"
update = modal.Function.lookup(DOCS_MODAL_INST_NAME, "daily_update")
search = modal.Function.lookup(DOCS_MODAL_INST_NAME, "search_vector_store")
write = modal.Function.lookup(DOCS_MODAL_INST_NAME, "write_documentation")
# print(write.call(doc_url))
results = search.call(
    doc_url,
    "In get_relevant_snippets parallelize the computation of the query embedding with the vector store. Do this using Modal primitives",
)
# metadatas = results["metadata"]
# docs = results["text"]
# vector_scores = results["score"]
# url_and_docs = [(metadata["url"], doc) for metadata, doc in zip(metadatas, docs)]
# ix = prepare_index_from_docs(url_and_docs)
# docs_to_scores = search_docs("How do I add random particles", ix)
# max_score = max(docs_to_scores.values())
# min_score = min(docs_to_scores.values()) if min(docs_to_scores.values()) < max_score else 0
# max_vector_score = max(vector_scores)
# min_vector_score = min(vector_scores) if min(vector_scores) < max_vector_score else 0
# text_to_final_score = []
# for idx, (url, doc) in enumerate(url_and_docs):
#     lexical_score = docs_to_scores[url] if url in docs_to_scores else 0
#     vector_score = vector_scores[idx]
#     normalized_lexical_score = (lexical_score - (min_score / 2)) / ((max_score + min_score))
#     normalized_vector_score = (vector_score - (min_vector_score / 2)) / ((max_vector_score + min_vector_score))
#     final_score = normalized_lexical_score * normalized_vector_score
#     text_to_final_score.append((doc, final_score))
# sorted_docs = sorted(text_to_final_score, key=lambda x: x[1], reverse=True)
# sorted_docs = [doc for doc, _ in sorted_docs]
# # get docs until you reach a 20k character count
# final_docs = []
# for doc in sorted_docs:
#     if len("".join(final_docs)) + len(doc) < 20000:
#         final_docs.append(doc)
#     else:
#         break
# new_docs = []
# for doc in docs:
#     if doc not in new_docs:
#         new_docs.append(doc)
# new_docs = new_docs[:min(5, len(new_docs))]
# for doc in new_docs:
#     print(doc + "\n\n\n")
# update.call()
