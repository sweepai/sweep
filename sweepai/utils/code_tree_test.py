import unittest

from sweepai.utils.code_tree import CodeTree


class TestCodeTree(unittest.TestCase):
    def test_get_lines_surrounding(self):
        code = """import math

def square_root(x):
    if x < 0:
        raise ValueError("Negative value")
    print(
        "hello world"
    )
    return math.sqrt(x)

print(square_root(4))
"""
        tree = CodeTree.from_code(code)

        # Line inside the 'import' statement
        result = tree.get_lines_surrounding(0)
        expected = (0, 0)
        self.assertEqual(result, expected)

        # Line not present
        result = tree.get_lines_surrounding(100)
        self.assertEqual(result, (100, 100))


if __name__ == "__main__":
    unittest.main()
