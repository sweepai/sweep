import os


def display_directory_tree(
    root_path,
    includes: list[str] = [],
    excludes: list[str] = [".git"],
):
    def display_directory_tree_helper(
        current_dir,
        indent="",
    ) -> str:
        files = os.listdir(current_dir)
        files.sort()
        tree = ""
        for item_name in files:
            full_path = os.path.join(current_dir, item_name)[len(root_path) + 1 :]
            if item_name in excludes:
                continue
            file_path = os.path.join(current_dir, item_name)
            if os.path.isdir(file_path):
                if full_path in includes:
                    tree += f"{indent}|- {item_name}/\n"
                    tree += display_directory_tree_helper(file_path, indent + "|   ")
                else:
                    tree += f"{indent}|- {item_name}/...\n"
            else:
                tree += f"{indent}|- {item_name}\n"
        return tree

    tree = display_directory_tree_helper(root_path)
    lines = tree.splitlines()
    return "\n".join([line[3:] for line in lines])


if __name__ == "__main__":
    tree = display_directory_tree(
        "forked_langchain",
        # includes=[
        #     'tests', 'tests/unit_tests', 'tests/unit_tests/callbacks', 'tests/unit_tests/callbacks/tracers', 'tests/unit_tests/callbacks/tracers/test_tracer.py'
        # ],
        includes=[
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/callbacks",
            "tests/unit_tests/callbacks/tracers",
            "tests/unit_tests/callbacks/tracers/test_tracer.py",
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/callbacks",
            "tests/unit_tests/callbacks/tracers",
            "tests/unit_tests/callbacks/tracers/test_tracer.py",
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/callbacks",
            "tests/unit_tests/callbacks/tracers",
            "tests/unit_tests/callbacks/tracers/test_tracer.py",
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/chains",
            "tests/unit_tests/chains/test_llm.py",
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/llms",
            "tests/unit_tests/llms/test_loading.py",
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/chains",
            "tests/unit_tests/chains/test_llm_summarization_checker.py",
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/callbacks",
            "tests/unit_tests/callbacks/tracers",
            "tests/unit_tests/callbacks/tracers/test_tracer.py",
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/prompts",
            "tests/unit_tests/prompts/test_length_based_example_selector.py",
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/chains",
            "tests/unit_tests/chains/test_sequential.py",
            "tests",
            "tests/unit_tests",
            "tests/unit_tests/callbacks",
            "tests/unit_tests/callbacks/tracers",
            "tests/unit_tests/callbacks/tracers/test_tracer.py",
        ],
    )
    print(tree)
