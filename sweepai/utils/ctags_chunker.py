import modal
import subprocess
import os

from sweepai.utils.ctags import Ctags

MAX_NUM_TAGS = 5

def unified_ctags_sorter(tags):
    # Define a unified priority map for both Python and JavaScript
    priority_map = {
        'module': 1,  # Python
        'namespace': 2,  # JavaScript/TypeScript
        'class': 3,  # Python, JavaScript, TypeScript
        'interface': 4,  # TypeScript
        'function': 5,  # Python, JavaScript, TypeScript
        'method': 6,  # Python, JavaScript, TypeScript
        'variable': 7,  # Python, JavaScript, TypeScript
        'constant': 8,  # JavaScript, TypeScript
        'member': 9,  # Python, JavaScript, TypeScript
        'enum': 10,  # TypeScript
        'property': 11  # JavaScript, TypeScript
    }

    # Sort the tags by priority, fallback to their original order for equal priorities
    sorted_tags = sorted(tags, key=lambda tag: (priority_map.get(tag[0], 5), tags.index(tag)))

    # Return the first MAX_NUM_TAGS tags
    return sorted_tags[:MAX_NUM_TAGS]

def should_add_tag(tag):
    if tag['kind'] == 'variable':
        return False
    if 'scope' not in tag and 'signature' in tag and len(tag['signature']) < 10:
        return False
    return True

def get_ctags_for_file(file_path):
    repo = Ctags(file_path)
    tags = repo.run_ctags()
    tag_structure = []
    for tag in tags:
        kind = tag['kind']
        name = tag['name']
        signature = None
        if 'signature' in tag:
            signature = tag['signature']
        if should_add_tag(tag):
            tag_structure.append((kind, name, signature))
    # Organize the tags by file and kind
    tag_structure = unified_ctags_sorter(tag_structure)

    # Generate the string
    output = ""
    for (kind, name, signature) in tag_structure:
        sig = ' ' + signature if signature else ''
        output += f"  {kind} {name}{sig}\n"
    return output