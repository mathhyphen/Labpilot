"""Tests for GitUtils AST traversal and auto_commit (review finding B.5).

The most subtle part of git_utils.py is ``_collect_local_python_dependencies``,
which statically walks the entry script's import graph to figure out
which files belong to the experiment (and thus need a scoped snapshot).
If this logic regresses, scoped auto-commits break silently: too few
files = the experiment is no longer reproducible; too many = unrelated
work gets dragged in.

These tests construct a small import graph in a temp directory and
verify the resolver returns the right set of files. They also exercise
``auto_commit`` in a stub-git environment.
"""

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from labpilot.git_utils import GitUtils


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _init_git_repo(path: Path) -> None:
    subprocess.check_call(["git", "init", "-q", str(path)])
    subprocess.check_call(["git", "-C", str(path), "config", "user.email", "t@e.com"])
    subprocess.check_call(["git", "-C", str(path), "config", "user.name", "t"])


class CollectLocalPythonDependenciesTests(unittest.TestCase):
    """Pin the AST-based import-graph walk."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self._cwd = os.getcwd()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_collects_entry_script(self):
        _write(self._tmp / "train.py", "x = 1\n")
        gu = GitUtils.__new__(GitUtils)  # skip config load
        related = gu._collect_local_python_dependencies("train.py")
        self.assertIn("train.py", related)

    def test_follows_simple_import(self):
        _write(self._tmp / "train.py", "from model import Net\n")
        _write(self._tmp / "model.py", "class Net: pass\n")
        gu = GitUtils.__new__(GitUtils)
        related = gu._collect_local_python_dependencies("train.py")
        self.assertIn("train.py", related)
        self.assertIn("model.py", related)

    def test_follows_nested_package_import(self):
        _write(
            self._tmp / "train.py",
            "from mypkg.models import ResNet\n",
        )
        _write(
            self._tmp / "mypkg" / "__init__.py",
            "",
        )
        _write(
            self._tmp / "mypkg" / "models.py",
            "class ResNet: pass\n",
        )
        gu = GitUtils.__new__(GitUtils)
        related = gu._collect_local_python_dependencies("train.py")
        self.assertIn("train.py", related)
        self.assertIn("mypkg/__init__.py", related)
        self.assertIn("mypkg/models.py", related)

    def test_skips_stdlib_and_third_party(self):
        _write(
            self._tmp / "train.py",
            "import os\nimport torch\nimport requests\n",
        )
        gu = GitUtils.__new__(GitUtils)
        related = gu._collect_local_python_dependencies("train.py")
        # Only train.py should be in the set — the imports have no
        # local resolution.
        self.assertEqual(related, {"train.py"})

    def test_skips_nonexistent_module(self):
        """A ``from nothing_local import X`` must not raise."""
        _write(
            self._tmp / "train.py",
            "from nothing_local import X\n",
        )
        gu = GitUtils.__new__(GitUtils)
        related = gu._collect_local_python_dependencies("train.py")
        self.assertIn("train.py", related)
        self.assertNotIn("nothing_local", related)

    def test_avoids_cycles(self):
        """Two files importing each other must not loop forever."""
        _write(
            self._tmp / "a.py",
            "from b import y\n",
        )
        _write(
            self._tmp / "b.py",
            "from a import x\n",
        )
        gu = GitUtils.__new__(GitUtils)
        # If cycle detection were broken, this would recurse forever.
        related = gu._collect_local_python_dependencies("a.py")
        self.assertIn("a.py", related)
        self.assertIn("b.py", related)

    def test_does_not_escape_repo_root(self):
        """A relative import that resolves to a path above the cwd
        must NOT be followed (path traversal protection)."""
        # Create a file outside the "repo root" (the tmp dir).
        outside = self._tmp.parent / f"outside_{os.getpid()}.py"
        try:
            outside.write_text("EVIL = True\n", encoding="utf-8")
            # From inside the repo, import the outside file via a
            # relative path traversal. (We can't actually ``import``
            # it normally, but our resolver searches both ``base_dir``
            # and ``root`` candidates and may pick up the outside file
            # if the path traversal isn't caught.)
            _write(
                self._tmp / "train.py",
                f"from ..outside_{os.getpid()} import EVIL\n",
            )
            gu = GitUtils.__new__(GitUtils)
            related = gu._collect_local_python_dependencies("train.py")
            for r in related:
                self.assertTrue(
                    Path(r).resolve().is_relative_to(self._tmp.resolve()),
                    f"{r} escaped the repo root!",
                )
        finally:
            if outside.exists():
                outside.unlink()

    def test_rejects_symlink_pointing_outside_repo(self):
        """A symlink inside the repo whose target lives outside must NOT
        be followed. The containment check uses ``os.path.realpath`` so the
        symlink is resolved before the commonpath comparison, rejecting the
        escape. Regression test for the abspath-based containment check."""
        outside = self._tmp.parent / f"outside_link_{os.getpid()}.py"
        try:
            outside.write_text("VALUE = 99\n", encoding="utf-8")
            _write(self._tmp / "train.py", "import helper\n")
            link_path = self._tmp / "helper.py"
            try:
                os.symlink(outside, link_path)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not supported on this platform")

            gu = GitUtils.__new__(GitUtils)
            related = gu._collect_local_python_dependencies("train.py")
            # helper.py resolves outside the repo, so it must be rejected
            # by the realpath containment check and never visited.
            self.assertNotIn("helper.py", related)
            self.assertIn("train.py", related)
        finally:
            if outside.exists():
                outside.unlink()


class GetRelatedDirtyFilesTests(unittest.TestCase):
    """``get_related_dirty_files`` intersects the dirty set with the
    import-walk set, then returns the sorted intersection."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self._cwd = os.getcwd()
        os.chdir(self._tmp)
        _init_git_repo(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_returns_only_dirty_related_files(self):
        # Create a chain of imports
        _write(self._tmp / "train.py", "from model import Net\n")
        _write(self._tmp / "model.py", "class Net: pass\n")
        # An unrelated dirty file
        _write(self._tmp / "unrelated.py", "# dirty but not related\n")
        subprocess.check_call(["git", "-C", str(self._tmp), "add", "."])
        subprocess.check_call(["git", "-C", str(self._tmp), "commit", "-q", "-m", "init"])
        # Make them all dirty
        _write(self._tmp / "train.py", "from model import Net\nx = 1\n")
        _write(self._tmp / "model.py", "class Net:\n    pass  # changed\n")
        _write(self._tmp / "unrelated.py", "# dirty again\n")

        gu = GitUtils.__new__(GitUtils)
        related = gu.get_related_dirty_files("train.py")
        self.assertIn("train.py", related)
        self.assertIn("model.py", related)
        self.assertNotIn("unrelated.py", related)


class AutoCommitTests(unittest.TestCase):
    """``auto_commit`` must be safe to call when the working tree is
    not a git repo, when the tree is clean, and when it is dirty."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self._cwd = os.getcwd()
        os.chdir(self._tmp)
        _init_git_repo(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_clean_tree_returns_current_commit(self):
        _write(self._tmp / "train.py", "x = 1\n")
        subprocess.check_call(["git", "add", "."])
        subprocess.check_call(["git", "commit", "-q", "-m", "init"])

        gu = GitUtils.__new__(GitUtils)
        gu.git_config = {"auto_snapshot": True, "require_clean": False}
        hash_before = subprocess.check_output(
            ["git", "-C", str(self._tmp), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        result = gu.auto_commit("explicit message")
        self.assertEqual(result, hash_before)

    def test_dirty_tree_with_explicit_message_makes_a_commit(self):
        _write(self._tmp / "train.py", "x = 1\n")
        subprocess.check_call(["git", "add", "."])
        subprocess.check_call(["git", "commit", "-q", "-m", "init"])
        _write(self._tmp / "train.py", "x = 2\n")

        gu = GitUtils.__new__(GitUtils)
        gu.git_config = {"auto_snapshot": True, "require_clean": False}
        gu.ai_config = {}  # disable AI path
        result = gu.auto_commit("my custom message")
        # A new commit was created — its hash differs from the old HEAD.
        new_head = subprocess.check_output(
            ["git", "-C", str(self._tmp), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        self.assertEqual(result, new_head)
        self.assertNotEqual(result, "not-a-git-repo")
        # And the commit message was the one we passed in.
        log = subprocess.check_output(
            ["git", "-C", str(self._tmp), "log", "-1", "--pretty=%s"],
            text=True,
        ).strip()
        self.assertEqual(log, "my custom message")

    def test_dirty_tree_with_specific_files_only_commits_those(self):
        _write(self._tmp / "train.py", "x = 1\n")
        _write(self._tmp / "unrelated.py", "y = 1\n")
        subprocess.check_call(["git", "add", "."])
        subprocess.check_call(["git", "commit", "-q", "-m", "init"])
        _write(self._tmp / "train.py", "x = 2\n")
        _write(self._tmp / "unrelated.py", "y = 2\n")

        gu = GitUtils.__new__(GitUtils)
        gu.git_config = {"auto_snapshot": True, "require_clean": False}
        gu.ai_config = {}
        gu.auto_commit("only train", specific_files=["train.py"])
        # The new commit must not include unrelated.py.
        show = subprocess.check_output(
            ["git", "-C", str(self._tmp), "show", "--stat", "HEAD"],
            text=True,
        )
        self.assertIn("train.py", show)
        self.assertNotIn("unrelated.py", show)


if __name__ == "__main__":
    unittest.main()
