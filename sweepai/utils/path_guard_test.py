import unittest

from sweepai.utils.path_guard import (
    DEFAULT_PROTECTED_PATHS,
    is_blocked,
    is_unsafe_repo_path,
    merge_protected_paths,
    sanitize_file_changes,
)


class TestIsBlocked(unittest.TestCase):
    def test_should_block_exact_file_match_when_path_is_in_blocked_dirs(self):
        result = is_blocked(
            "sweepai/core/prompts.py",
            ["sweepai/core/prompts.py"],
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["path"], "sweepai/core/prompts.py")

    def test_should_block_nested_file_when_parent_directory_is_blocked(self):
        result = is_blocked("src/secrets/tokens.py", ["src/secrets"])
        self.assertTrue(result["success"])

    def test_should_not_block_unrelated_file_when_name_only_shares_prefix(self):
        result = is_blocked("testimonial.py", ["test"])
        self.assertFalse(result["success"])

    def test_should_block_github_workflow_when_default_protected_paths_used(self):
        result = is_blocked(
            ".github/workflows/malicious.yml",
            list(DEFAULT_PROTECTED_PATHS),
        )
        self.assertTrue(result["success"])

    def test_should_block_github_action_when_default_protected_paths_used(self):
        result = is_blocked(
            ".github/actions/evil/action.yml",
            list(DEFAULT_PROTECTED_PATHS),
        )
        self.assertTrue(result["success"])

    def test_should_not_block_other_github_file_when_only_ci_paths_are_protected(self):
        result = is_blocked(
            ".github/CODEOWNERS",
            list(DEFAULT_PROTECTED_PATHS),
        )
        self.assertFalse(result["success"])

    def test_should_block_path_traversal_when_relative_escape_is_used(self):
        result = is_blocked("../../.github/workflows/evil.yml", [])
        self.assertTrue(result["success"])

    def test_should_block_absolute_path_when_file_path_is_absolute(self):
        result = is_blocked("/tmp/evil.yml", [])
        self.assertTrue(result["success"])

    def test_should_block_disguised_workflow_when_dotdot_is_normalized(self):
        result = is_blocked(
            ".github/workflows/../workflows/evil.yml",
            list(DEFAULT_PROTECTED_PATHS),
        )
        self.assertTrue(result["success"])


class TestIsUnsafeRepoPath(unittest.TestCase):
    def test_should_return_true_when_path_contains_parent_directory(self):
        self.assertTrue(is_unsafe_repo_path("../secrets.env"))

    def test_should_return_true_when_path_is_empty(self):
        self.assertTrue(is_unsafe_repo_path(""))

    def test_should_return_false_when_path_is_a_normal_repo_file(self):
        self.assertFalse(is_unsafe_repo_path("src/app.py"))


class TestMergeProtectedPaths(unittest.TestCase):
    def test_should_include_default_ci_paths_and_user_blocked_dirs(self):
        protected_paths = merge_protected_paths(["sweepai/core/prompts.py"])
        self.assertIn(".github/workflows", protected_paths)
        self.assertIn(".github/actions", protected_paths)
        self.assertIn("sweepai/core/prompts.py", protected_paths)

    def test_should_keep_default_ci_paths_when_user_blocked_dirs_are_empty(self):
        protected_paths = merge_protected_paths([])
        self.assertEqual(protected_paths, list(DEFAULT_PROTECTED_PATHS))


class TestSanitizeFileChanges(unittest.TestCase):
    def test_should_keep_valid_source_file_when_path_is_not_protected(self):
        file_changes = {"src/app.py": "print('ok')"}
        sanitized, file_removed, rejected_paths = sanitize_file_changes(
            file_changes,
            ["src/app.py"],
            list(DEFAULT_PROTECTED_PATHS),
        )
        self.assertEqual(sanitized, file_changes)
        self.assertFalse(file_removed)
        self.assertEqual(rejected_paths, [])

    def test_should_reject_workflow_file_when_fcr_tries_to_create_malicious_ci(self):
        workflow_path = ".github/workflows/malicious.yml"
        file_changes = {
            workflow_path: "on: push\njobs:\n  exfil:\n    runs-on: ubuntu-latest\n",
            "src/app.py": "print('ok')",
        }
        sanitized, file_removed, rejected_paths = sanitize_file_changes(
            file_changes,
            [workflow_path, "src/app.py"],
            list(DEFAULT_PROTECTED_PATHS),
        )
        self.assertNotIn(workflow_path, sanitized)
        self.assertEqual(sanitized, {"src/app.py": "print('ok')"})
        self.assertTrue(file_removed)
        self.assertIn(workflow_path, rejected_paths)

    def test_should_reject_user_blocked_file_when_blocked_dirs_are_configured(self):
        blocked_file = "sweepai/core/prompts.py"
        protected_paths = merge_protected_paths([blocked_file])
        file_changes = {blocked_file: "stolen"}
        sanitized, file_removed, rejected_paths = sanitize_file_changes(
            file_changes,
            [blocked_file],
            protected_paths,
            file_exists=lambda _path: True,
        )
        self.assertEqual(sanitized, {})
        self.assertTrue(file_removed)
        self.assertIn(blocked_file, rejected_paths)

    def test_should_reject_existing_repo_workflow_when_file_already_exists(self):
        workflow_path = ".github/workflows/ci.yml"
        file_changes = {workflow_path: "on: push\n"}
        sanitized, file_removed, rejected_paths = sanitize_file_changes(
            file_changes,
            [workflow_path],
            list(DEFAULT_PROTECTED_PATHS),
            file_exists=lambda _path: True,
        )
        self.assertEqual(sanitized, {})
        self.assertTrue(file_removed)
        self.assertIn(workflow_path, rejected_paths)

    def test_should_reject_path_traversal_when_workflow_is_disguised_with_dotdots(self):
        traversal_path = "src/../../.github/workflows/evil.yml"
        file_changes = {traversal_path: "on: push\n"}
        sanitized, file_removed, rejected_paths = sanitize_file_changes(
            file_changes,
            [traversal_path],
            list(DEFAULT_PROTECTED_PATHS),
        )
        self.assertEqual(sanitized, {})
        self.assertTrue(file_removed)
        self.assertIn(traversal_path, rejected_paths)

    def test_should_drop_unknown_file_when_it_is_not_in_fcrs_or_repo(self):
        file_changes = {"src/orphan.py": "print('nope')"}
        sanitized, file_removed, rejected_paths = sanitize_file_changes(
            file_changes,
            ["src/app.py"],
            list(DEFAULT_PROTECTED_PATHS),
        )
        self.assertEqual(sanitized, {})
        self.assertTrue(file_removed)
        self.assertEqual(rejected_paths, [])


if __name__ == "__main__":
    unittest.main()
