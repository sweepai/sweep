from sweepai.config.server import DB_MODAL_INST_NAME


import modal

stub = modal.Stub(DB_MODAL_INST_NAME)

get_relevant_snippets = modal.Function.lookup(
    DB_MODAL_INST_NAME, "get_relevant_snippets"
)

test_query = "When there's an empty repository in on_ticket.py, leave a clear error message that Sweep doesn't work on empty repositories"
get_relevant_snippets.call(
    repo_name="sweepai/sweep",
    query=test_query,
    n_results=5,
    installation_id=36855882,
    username="wwzeng1",
)
