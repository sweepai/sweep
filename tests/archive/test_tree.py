from sweepai.core.context_pruning import ContextToPrune
from sweepai.utils.tree_utils import DirectoryTree

tree_str = """"""


response = """
"""

context_to_prune = ContextToPrune.from_string(response)

tree = DirectoryTree()
tree.parse(tree_str)
serialized_list = ["docs/pages/"]
# tree.remove_all_not_included(context_to_prune.paths_to_keep)
tree.remove_all_not_included([])
# print()
# print(tree)

# tree.expand_directory(context_to_prune.directories_to_expand)
tree.expand_directory(serialized_list)
print()
print(tree)
