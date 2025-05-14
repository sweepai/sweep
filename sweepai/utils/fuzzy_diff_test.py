import unittest
from sweepai.utils.fuzzy_diff import patience_fuzzy_diff

class TestPatienceFuzzyDiff(unittest.TestCase):

    def test_empty_strings(self):
        self.assertEqual(patience_fuzzy_diff("", ""), "")

    def test_identical_strings(self):
        text = "Line1\nLine2\nLine3"
        self.assertEqual(patience_fuzzy_diff(text, text), "")

    def test_addition_at_end(self):
        original = "Line1\nLine2"
        modified = "Line1\nLine2\nLine3"
        self.assertEqual(patience_fuzzy_diff(original, modified), "  Line1\n  Line2\n+ Line3")

    def test_deletion_at_beginning(self):
        original = "Line1\nLine2\nLine3"
        modified = "Line2\nLine3"
        self.assertEqual(patience_fuzzy_diff(original, modified), "- Line1\n  Line2\n  Line3")

    def test_replacement(self):
        original = "Line1\nLine2\nLine3"
        modified = "Line1\nLine4\nLine3"
        self.assertEqual(patience_fuzzy_diff(original, modified), "  Line1\n- Line2\n+ Line4\n  Line3")

    def test_multiple_modifications(self):
        original = "Line1\nLine2\nLine3\nLine4"
        modified = "Line0\nLine2\nLine3Modified\nLine5"
        self.assertEqual(patience_fuzzy_diff(original, modified), "- Line1\n+ Line0\n  Line2\n- Line3\n+ Line3Modified\n- Line4\n+ Line5")

    def test_whitespace_differences(self):
        original = "Line1 \nLine2"
        modified = "Line1\nLine2 "
        self.assertEqual(patience_fuzzy_diff(original, modified), "- Line1 \n+ Line1\n- Line2\n+ Line2 ")

    def test_case_sensitivity(self):
        original = "Line1\nLine2"
        modified = "line1\nline2"
        self.assertEqual(patience_fuzzy_diff(original, modified), "- Line1\n+ line1\n- Line2\n+ line2")

    def test_empty_line_replacement(self):
        original = "Line1\n\nLine3"
        modified = "Line1\nLine2\nLine3"
        self.assertEqual(patience_fuzzy_diff(original, modified), "  Line1\n- \n+ Line2\n  Line3")

    def test_all_lines_changed(self):
        original = "Line1\nLine2"
        modified = "NewLine1\nNewLine2"
        self.assertEqual(patience_fuzzy_diff(original, modified), "- Line1\n+ NewLine1\n- Line2\n+ NewLine2")

    def test_line_addition_and_deletion(self):
        original = "Line1\nLine2\nLine3"
        modified = "Line1\nLine3"
        self.assertEqual(patience_fuzzy_diff(original, modified), "  Line1\n- Line2\n  Line3")

    def test_fuzzy_matching(self):
        original = "Line1 slightly different\nLine2\nLine3"
        modified = "Line1 very different\nLine2\nLine3"
        self.assertEqual(patience_fuzzy_diff(original, modified), "- Line1 slightly different\n+ Line1 very different\n  Line2\n  Line3")


if __name__ == '__main__':
    unittest.main()
