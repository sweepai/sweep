import modal

if __name__ == "__main__":
    app = "dev-db"
    repo = "sweepai/forked_langchain"
    # init_index = modal.Function.lookup(app, "init_index")
    # init_index.call(repo, ["src"], [], [".py"], [], 36855882)

    get_relevant_file_paths = modal.Function.lookup(app, "get_relevant_file_paths")
    print(get_relevant_file_paths.call(repo, "Idea: A memory similar to ConversationBufferWindowMemory but utilizing token length #1598", 5))

def test_compute():
    from src.core.vector_db import Embedding

    # Create an instance of the Embedding class
    embedding = Embedding()

    # Create a list of texts
    texts = ["This is a test.", "Another test.", "This text will cause an error."]

    # Call the compute function with the list of texts
    embeddings = embedding.compute(texts)

    # Check that the function returns the correct embeddings
    assert len(embeddings) == len(texts)
    for embedding in embeddings[:-1]:
        assert isinstance(embedding, list)
        assert all(isinstance(e, float) for e in embedding)

    # Check that the function logs an error and returns None for the last text
    assert embeddings[-1] is None

test_compute()

