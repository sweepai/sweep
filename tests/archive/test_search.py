from sweepai.config.server import DB_MODAL_INST_NAME


import modal

stub = modal.Stub(DB_MODAL_INST_NAME)

get_relevant_snippets = modal.Function.lookup(
    DB_MODAL_INST_NAME, "get_relevant_snippets"
)

dev = 36855882
staging = 40419656

test_query = """Sweep: Fix Uncaught SyntaxError: Unexpected token '&' (at examples:14:21). https://github.com/sweepai/sweep/blob/d9d53a78b4fab18b89e4003268cf6ba50da4f068/docs/theme.config.tsx#L15

Fix Uncaught SyntaxError: Unexpected token '&' (at examples:14:21)
In docs/theme.config.tsx"""
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
for result in lexical[:5]:
    print(result)
print("Vector Results:")
for result in vector[:5]:
    print(result)
