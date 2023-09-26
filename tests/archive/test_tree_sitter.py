import subprocess

from tree_sitter import Language

subprocess.run(
    f"git clone https://github.com/tree-sitter/tree-sitter-embedded-template cache/tree-sitter-embedded-template",
    shell=True,
)
Language.build_library(
    f"/tmp/cache/build/embedded-template.so",
    [f"/tmp/cache/tree-sitter-embedded-template"],
)
subprocess.run(
    f"cp cache/build/embedded-template.so /tmp/embedded-template.so", shell=True
)
language = Language("/tmp/embedded-template.so", "embedded_template")
