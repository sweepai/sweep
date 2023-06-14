import modal

if __name__ == "__main__":
    app = "dev-db"
    repo = "sweepai/forked_langchain"
    # init_index = modal.Function.lookup(app, "init_index")
    # init_index.call(repo, ["src"], [], [".py"], [], 36855882)

    get_relevant_file_paths = modal.Function.lookup(app, "get_relevant_file_paths")
    print(get_relevant_file_paths.call(repo, "Idea: A memory similar to ConversationBufferWindowMemory but utilizing token length #1598", 5))
