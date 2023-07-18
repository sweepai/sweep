import modal
import subprocess
import os

from sweepai.utils.ctags import Ctags

image_with_ctags_and_code = (
    modal.Image.debian_slim()
    .pip_install("rapidfuzz")
    .run_commands(
        "apt-get update && apt-get install -y universal-ctags",
        'export PATH="/usr/local/bin:$PATH"'
    )
)


stub = modal.Stub("dev_tags")

@stub.function(image=image_with_ctags_and_code)
def run(user_query):

    # Generate the tags
    repo = Ctags("/tmp/code/test_directory/test.py")
    tags = repo.run_ctags()
    # Organize the tags by file and kind
    tag_structure = {}
    for tag in tags:
        path = tag['path']
        kind = tag['kind']
        name = tag['name']

        if path not in tag_structure:
            tag_structure[path] = {}

        if kind not in tag_structure[path]:
            tag_structure[path][kind] = []

        tag_structure[path][kind].append(name)

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
    print(output)

@stub.local_entrypoint()
def f():
    res = run("test")
    import pdb; pdb.set_trace()