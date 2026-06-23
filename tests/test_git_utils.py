import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from labpilot.git_utils import GitRequireCleanError, GitUtils


def run_git(args, cwd):
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


class GitUtilsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        self.old_cwd = os.getcwd()
        os.chdir(self.repo)

        run_git(["init"], self.repo)
        run_git(["config", "user.email", "labpilot@example.com"], self.repo)
        run_git(["config", "user.name", "LabPilot Tests"], self.repo)

        (self.repo / "train.py").write_text(
            "import helper\nprint(helper.VALUE)\n", encoding="utf-8"
        )
        (self.repo / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.repo / "other.py").write_text("VALUE = 1\n", encoding="utf-8")
        run_git(["add", "."], self.repo)
        run_git(["commit", "-m", "test: baseline"], self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def test_related_dirty_files_include_only_entry_script_and_local_imports(self):
        (self.repo / "train.py").write_text(
            "import helper\nprint(helper.VALUE + 1)\n", encoding="utf-8"
        )
        (self.repo / "helper.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.repo / "other.py").write_text("VALUE = 2\n", encoding="utf-8")

        git_utils = GitUtils()

        self.assertEqual(
            git_utils.get_related_dirty_files("train.py"),
            ["helper.py", "train.py"],
        )

    def test_auto_commit_with_specific_files_leaves_unrelated_staged_file_out(self):
        (self.repo / "train.py").write_text(
            "import helper\nprint(helper.VALUE + 1)\n", encoding="utf-8"
        )
        (self.repo / "helper.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.repo / "other.py").write_text("VALUE = 2\n", encoding="utf-8")
        run_git(["add", "other.py"], self.repo)

        git_utils = GitUtils()
        git_utils.generate_ai_commit_message = lambda diff: "test: snapshot training script"

        git_utils.auto_commit(specific_files=["helper.py", "train.py"])

        result = run_git(["show", "--name-only", "--pretty=format:", "HEAD"], self.repo)
        committed_files = {line.strip() for line in result.stdout.splitlines() if line.strip()}

        self.assertEqual(committed_files, {"helper.py", "train.py"})
        status = run_git(["status", "--porcelain"], self.repo).stdout
        self.assertIn("other.py", status)

    def test_require_clean_raises_specific_error_type(self):
        """git.require_clean must raise GitRequireCleanError (not a bare
        Exception) so cli.py can catch it by type instead of string-matching
        ``str(e)``. Regression test for the stringly-typed control flow."""
        (self.repo / "train.py").write_text(
            "import helper\nprint(helper.VALUE + 1)\n", encoding="utf-8"
        )

        git_utils = GitUtils()
        git_utils.git_config = {"auto_snapshot": True, "require_clean": True}

        with self.assertRaises(GitRequireCleanError):
            git_utils.check_and_handle_repo(specific_files=["train.py"])

    def test_require_clean_error_is_not_caught_by_generic_exception_check(self):
        """A bare ``except Exception`` that re-checks ``isinstance`` must
        not falsely match GitRequireCleanError when require_clean is False —
        and the error must carry the require_clean hint in its message so
        existing string-based cli.py detection still works during transition."""
        (self.repo / "train.py").write_text(
            "import helper\nprint(helper.VALUE + 1)\n", encoding="utf-8"
        )

        git_utils = GitUtils()
        git_utils.git_config = {"auto_snapshot": True, "require_clean": True}

        raised = None
        try:
            git_utils.check_and_handle_repo(specific_files=["train.py"])
        except Exception as exc:  # noqa: BLE001 — intentional for the test
            raised = exc

        self.assertIsInstance(raised, GitRequireCleanError)
        self.assertIn("require_clean", str(raised))


if __name__ == "__main__":
    unittest.main()
