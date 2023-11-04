import unittest
from sweepai.handlers.on_pr_commit import handle_pr_commit

class TestHandlePRCommit(unittest.TestCase):
    def test_handle_pr_commit(self):
        try:
            handle_pr_commit()
        except Exception as e:
            self.fail(f"handle_pr_commit raised an exception: {e}")
