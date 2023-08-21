from sweepai.config.server import DB_MODAL_INST_NAME


import modal

stub = modal.Stub(DB_MODAL_INST_NAME)

get_relevant_snippets = modal.Function.lookup(
    DB_MODAL_INST_NAME, "get_relevant_snippets"
)

dev = 36855882
staging = 40419656

test_query = "make multiple passes of self review using chat_logger"
lexical = get_relevant_snippets.call(
    repo_name="sweepai/sweep",
    query=test_query,
    n_results=5,
    installation_id=dev,
    username="wwzeng1",
    lexical=True,
)
vector = get_relevant_snippets.call(
    repo_name="sweepai/sweep",
    query=test_query,
    n_results=5,
    installation_id=dev,
    username="wwzeng1",
    lexical=False,
)

# format vector and lexical titles one by one
print("Lexical Results:")
for result in lexical:
    print(result)
print("Vector Results:")
for result in vector:
    print(result)
