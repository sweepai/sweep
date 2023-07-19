import modal
import subprocess
import os

from sweepai.utils.ctags import Ctags

def get_ctags_for_file(file_path):
    repo = Ctags(file_path)
    tags = repo.run_ctags()
    # Organize the tags by file and kind
    tag_structure = {}
    for tag in tags:
        path = tag['path']
        kind = tag['kind']
        name = tag['name']
        signature = tag['signature']

        if path not in tag_structure:
            tag_structure[path] = {}

        if kind not in tag_structure[path]:
            tag_structure[path][kind] = []

        tag_structure[path][kind].append(name)
        tag_structure[path][kind].append(signature)

    # Generate the string
    output = ""
    for path, kinds in tag_structure.items():
        # Get the file name from the path
        filename = path.split('/')[-1]

        output += f"{filename}:\n"
        for kind, names in kinds.items():
            output += f"   {kind}\n"
            for name in names:
                output += f"      {name}\n"
        output += "...\n"
    return output