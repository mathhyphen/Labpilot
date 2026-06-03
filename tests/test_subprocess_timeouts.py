"""Regression tests ensuring subprocess.run calls always carry a timeout.

Background: a hung child (driver bug, NFS stall, frozen nvidia-smi) used
to be able to block labrun forever because none of the git / nvidia-smi
subprocess.run invocations had a ``timeout=`` argument. We assert here
that every call to subprocess.run from labpilot modules passes one.

The test inspects the *call args* of every subprocess.run invocation
executed by each tested function. This is a behavioral assertion: even
if a future refactor changes the order of kwargs, the test fails if
``timeout`` is missing.
"""
import os
import subprocess
import unittest
from unittest.mock import patch, MagicMock


def _completed_proc(returncode=0, stdout="", stderr=""):
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


class GitUtilsSubprocessTimeoutTests(unittest.TestCase):
    """Each git_utils method should hand a timeout to subprocess.run."""

    def _assert_timeout(self, captured_calls, label):
        for i, call in enumerate(captured_calls):
            kwargs = call.kwargs
            self.assertIn(
                "timeout",
                kwargs,
                f"[{label}] subprocess.run call #{i} missing timeout kwarg; "
                f"got kwargs={list(kwargs.keys())}",
            )
            self.assertIsNotNone(
                kwargs["timeout"],
                f"[{label}] subprocess.run call #{i} has timeout=None",
            )
            self.assertGreater(
                kwargs["timeout"],
                0,
                f"[{label}] subprocess.run call #{i} timeout must be > 0",
            )

    @patch("labpilot.git_utils.subprocess.run")
    def test_is_git_repo_passes_timeout(self, run):
        from labpilot.git_utils import GitUtils
        run.return_value = _completed_proc(returncode=0)
        GitUtils().is_git_repo()
        self._assert_timeout(run.call_args_list, "is_git_repo")

    @patch("labpilot.git_utils.subprocess.run")
    def test_get_git_info_passes_timeout(self, run):
        from labpilot.git_utils import GitUtils
        run.side_effect = [
            _completed_proc(stdout=".git\n"),       # is_git_repo
            _completed_proc(stdout="abc123\n"),    # rev-parse HEAD
            _completed_proc(stdout="msg\n"),       # log -1
        ]
        GitUtils().get_git_info()
        self._assert_timeout(run.call_args_list, "get_git_info")

    @patch("labpilot.git_utils.subprocess.run")
    def test_is_dirty_passes_timeout(self, run):
        from labpilot.git_utils import GitUtils
        run.side_effect = [
            _completed_proc(stdout=".git\n"),
            _completed_proc(stdout=""),
        ]
        GitUtils().is_dirty()
        self._assert_timeout(run.call_args_list, "is_dirty")

    @patch("labpilot.git_utils.subprocess.run")
    def test_get_dirty_files_passes_timeout(self, run):
        from labpilot.git_utils import GitUtils
        run.side_effect = [
            _completed_proc(stdout=".git\n"),
            _completed_proc(stdout=""),
        ]
        GitUtils().get_dirty_files()
        self._assert_timeout(run.call_args_list, "get_dirty_files")


class CliSubprocessTimeoutTests(unittest.TestCase):
    """cli.py nvidia-smi call should hand a timeout to subprocess.run."""

    @patch("labpilot.cli.subprocess.run")
    def test_get_free_gpus_passes_timeout(self, run):
        from labpilot.cli import get_free_gpus
        run.return_value = _completed_proc(
            stdout="0, 8192\n1, 4096\n",
            returncode=0,
        )
        get_free_gpus(2048)
        self.assertTrue(run.called)
        self.assertIn("timeout", run.call_args.kwargs)
        self.assertGreater(run.call_args.kwargs["timeout"], 0)


if __name__ == "__main__":
    unittest.main()
