class TestSnippet(unittest.TestCase):
    # existing tests...

    def test_add(self):
        snippet1 = Snippet(content="line1\nline2\nline3", start=1, end=2, file_path="test.py")
        snippet2 = Snippet(content="line1\nline2\nline3", start=2, end=3, file_path="test.py")
        result = snippet1 + snippet2
        self.assertEqual(result.start, 1)
        self.assertEqual(result.end, 3)

    def test_xor(self):
        snippet1 = Snippet(content="line1\nline2\nline3", start=1, end=2, file_path="test.py")
        snippet2 = Snippet(content="line1\nline2\nline3", start=2, end=3, file_path="test.py")
        self.assertTrue(snippet1 ^ snippet2)
        snippet3 = Snippet(content="line1\nline2\nline3", start=3, end=4, file_path="test.py")
        self.assertFalse(snippet1 ^ snippet3)

    def test_or(self):
        snippet1 = Snippet(content="line1\nline2\nline3", start=1, end=2, file_path="test.py")
        snippet2 = Snippet(content="line1\nline2\nline3", start=2, end=3, file_path="test.py")
        result = snippet1 | snippet2
        self.assertEqual(result.start, 1)
        self.assertEqual(result.end, 3)

if __name__ == "__main__":
    unittest.main()
</new_file>