import modal

from sweepai.utils.constants import UTILS_NAME

code_examples = ["""
import numpy as np

# this is a file

a = 1

def main():
    pass

def test():
    print("test")
""", """
// example java

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello World!");
    }
}
""", """

// this is javascript

const a = 1;

function main() {
    console.log(a);
}

var test = () => {
    console.log("test");
    const b = 2;
}
"""]

test_string = """
## Hello world

Test
"""

if __name__ == "__main__":
    chunk_string = modal.Function.lookup(UTILS_NAME, "Chunking.chunk")
    files = [
        "tests/example_code/chroma_fastapi.py", 
        "tests/example_code/query_builder.tsx",
        "tests/example_code/factorial.rb"
    ]
    for file in files:
        code_example = open(file).read()
        chunks, metadata, ids = chunk_string.call(code_example, file)
        store_path = file + ".chunks.txt"
        with open(store_path, "w") as f:
            for chunk in chunks:
                f.write(chunk + "\n======================\n")

    chunks, metadata, ids = chunk_string.call(test_string, "test.txt")
