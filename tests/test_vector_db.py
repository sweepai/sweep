import modal

if __name__ == "__main__":
    app = "dev-db"
    repo = "sweepai/forked_langchain"
    # init_index = modal.Function.lookup(app, "init_index")
    # init_index.call(repo, ["src"], [], [".py"], [], 36855882)

    get_relevant_file_paths = modal.Function.lookup(app, "get_relevant_file_paths")
    print(get_relevant_file_paths.call(repo, "Idea: A memory similar to ConversationBufferWindowMemory but utilizing token length #1598", 5))

def test_get_deeplake_vs_from_repo_exclusion():
    # Set up temporary repo with a set of files
    # ...

    # Set up exclusion list
    exclusion_list = ['excluded_file_1', 'excluded_file_2']

    # Call get_deeplake_vs_from_repo with the temporary repo and a SweepConfig object with the exclusion list
    sweep_config = SweepConfig(exclude_files=exclusion_list)
    deeplake_vs = get_deeplake_vs_from_repo('temp_repo', sweep_config)

    # Check that the returned vector store does not contain the excluded files
    for file in exclusion_list:
        assert file not in deeplake_vs

    # Clean up temporary repo
    # ...

def get_deeplake_vs_from_repo(repo, sweep_config):
    # Implementation of get_deeplake_vs_from_repo
    # ...

class SweepConfig:
    def __init__(self, exclude_files):
        self.exclude_files = exclude_files

    # Other methods of SweepConfig
    # ...