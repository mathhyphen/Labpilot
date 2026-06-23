"""Tests for the OpenClawCliNotifier (personal WeChat via OpenClaw CLI).

OpenClaw is Tencent's official AI gateway that integrates with personal
WeChat via the ClawBot plugin (iLink protocol). The LabPilot notifier
is a thin wrapper around ``openclaw send <user_id> --message <text>``
so users with an existing OpenClaw deployment can route experiment
notifications to their personal WeChat.
"""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from labpilot.notify import OpenClawCliNotifier


def _completed(returncode=0, stdout="", stderr=""):
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


class OpenClawCliNotifierTests(unittest.TestCase):
    def _notifier(self, **cfg):
        return OpenClawCliNotifier({"notification": {"openclaw": {"user_id": "user-x", **cfg}}})

    @patch("labpilot.notify.subprocess.run")
    def test_calls_openclaw_send_with_user_and_message(self, run):
        """The CLI must receive the user_id and a combined title/body message.

        The resolved binary may be an absolute path (from shutil.which)
        or the literal "openclaw" if the test environment has it on
        PATH. We just assert the basename starts with "openclaw".
        """
        run.return_value = _completed(returncode=0)
        notifier = self._notifier()

        self.assertTrue(notifier.send_notification("标题", "正文内容"))

        args, kwargs = run.call_args
        cmd = args[0]
        import os

        self.assertTrue(
            os.path.basename(cmd[0]).lower().startswith("openclaw"),
            f"cmd[0]={cmd[0]!r} should resolve to an openclaw binary",
        )
        # The "send" subcommand and its flag/argument structure should
        # be preserved.
        self.assertIn("send", cmd)
        self.assertIn("user-x", cmd)
        self.assertIn("--message", cmd)
        msg_index = cmd.index("--message") + 1
        self.assertIn("标题", cmd[msg_index])
        self.assertIn("正文内容", cmd[msg_index])
        self.assertGreater(kwargs.get("timeout", 0), 0)

    @patch("labpilot.notify.subprocess.run")
    def test_uses_custom_cli_path(self, run):
        """When the user configures an absolute cli_path, that exact
        path is passed to subprocess.run.

        We mock ``os.path.isfile`` so the test doesn't depend on
        ``/opt/openclaw/bin/openclaw`` actually existing on the
        test host.
        """
        run.return_value = _completed(returncode=0)
        custom_path = "/opt/openclaw/bin/openclaw"
        notifier = self._notifier(cli_path=custom_path)
        with patch("labpilot.notify.os.path.isfile", return_value=True):
            notifier.send_notification("t", "m")
        args, _ = run.call_args
        self.assertEqual(args[0][0], custom_path)

    @patch("labpilot.notify.subprocess.run")
    def test_uses_custom_cli_path_when_isfile_works_on_windows(self, run):
        """Regression: on Windows, ``os.path.isabs("/opt/x")`` returns
        False so the old code fell through to ``shutil.which`` and
        rejected the path even when the file existed. The new resolver
        must check ``os.path.isfile`` first regardless of whether the
        path looks absolute to the host OS.
        """
        run.return_value = _completed(returncode=0)
        # An absolute-looking path that on Windows ``os.path.isabs``
        # would still consider non-absolute (no drive letter). We patch
        # ``isabs`` to return False explicitly to simulate the
        # cross-platform mismatch.
        custom_path = "/opt/openclaw/bin/openclaw"
        notifier = self._notifier(cli_path=custom_path)
        with (
            patch("labpilot.notify.os.path.isfile", return_value=True),
            patch("labpilot.notify.os.path.isabs", return_value=False),
        ):
            notifier.send_notification("t", "m")
        args, _ = run.call_args
        self.assertEqual(args[0][0], custom_path)

    @patch("labpilot.notify.subprocess.run")
    def test_uses_configured_timeout(self, run):
        run.return_value = _completed(returncode=0)
        notifier = self._notifier(timeout=7)
        notifier.send_notification("t", "m")
        _, kwargs = run.call_args
        self.assertEqual(kwargs["timeout"], 7)

    def test_missing_user_id_returns_false_without_calling_cli(self):
        notifier = OpenClawCliNotifier({"notification": {"openclaw": {}}})
        # No CLI invocation should be attempted.
        with patch("labpilot.notify.subprocess.run") as run:
            self.assertFalse(notifier.send_notification("t", "m"))
            run.assert_not_called()

    @patch("labpilot.notify.subprocess.run")
    def test_nonzero_return_code_treated_as_failure(self, run):
        run.return_value = _completed(returncode=1, stderr="some error")
        notifier = self._notifier()
        self.assertFalse(notifier.send_notification("t", "m"))

    @patch("labpilot.notify.subprocess.run")
    def test_file_not_found_returns_false(self, run):
        run.side_effect = FileNotFoundError("openclaw not found")
        notifier = self._notifier()
        self.assertFalse(notifier.send_notification("t", "m"))

    @patch("labpilot.notify.subprocess.run")
    def test_timeout_returns_false(self, run):
        run.side_effect = subprocess.TimeoutExpired(cmd=["openclaw"], timeout=10)
        notifier = self._notifier()
        self.assertFalse(notifier.send_notification("t", "m"))

    # --- Review finding C2: cli_path validation ---

    def test_rejects_cli_path_pointing_at_non_openclaw_binary(self):
        """A config that sets ``cli_path`` to e.g. ``rm`` must be refused.

        The basename check prevents an attacker who can edit
        ``~/.labpilot.yaml`` from turning every labrun into a silent
        arbitrary-execution vector.
        """
        notifier = OpenClawCliNotifier(
            {
                "notification": {
                    "openclaw": {
                        "user_id": "u1",
                        "cli_path": "/bin/rm",
                    }
                }
            }
        )
        with patch("labpilot.notify.subprocess.run") as run:
            self.assertFalse(notifier.send_notification("t", "m"))
            run.assert_not_called()

    def test_rejects_cli_path_that_does_not_resolve(self):
        notifier = OpenClawCliNotifier(
            {
                "notification": {
                    "openclaw": {
                        "user_id": "u1",
                        "cli_path": "/nonexistent/openclaw-fake",
                    }
                }
            }
        )
        with patch("labpilot.notify.subprocess.run") as run:
            self.assertFalse(notifier.send_notification("t", "m"))
            run.assert_not_called()

    def test_rejects_user_id_starting_with_dash(self):
        """``--help``-style user_id would inject CLI flags.

        subprocess.run with list form is safe from shell injection but
        not from argument smuggling, since the CLI parses argv itself.
        """
        notifier = OpenClawCliNotifier(
            {
                "notification": {
                    "openclaw": {
                        "user_id": "--help",
                    }
                }
            }
        )
        with patch("labpilot.notify.subprocess.run") as run:
            self.assertFalse(notifier.send_notification("t", "m"))
            run.assert_not_called()

    def test_rejects_user_id_with_whitespace(self):
        notifier = OpenClawCliNotifier(
            {
                "notification": {
                    "openclaw": {
                        "user_id": "user one",
                    }
                }
            }
        )
        with patch("labpilot.notify.subprocess.run") as run:
            self.assertFalse(notifier.send_notification("t", "m"))
            run.assert_not_called()

    @patch("labpilot.notify.subprocess.run")
    def test_os_error_during_exec_returns_false(self, run):
        """OSError from subprocess.run must surface as False, not crash.

        Regression for the broken diagnostic that logged
        ``type(__import__("builtins").Exception).__name__`` (the
        literal "type") instead of the real exception class. We patch
        ``os.path.isfile`` so ``_resolve_cli`` accepts the configured
        path and execution reaches ``subprocess.run``, which then
        raises OSError.
        """
        run.side_effect = OSError("exec failed")
        notifier = self._notifier(cli_path="/opt/openclaw/bin/openclaw")
        with patch("labpilot.notify.os.path.isfile", return_value=True):
            self.assertFalse(notifier.send_notification("t", "m"))


if __name__ == "__main__":
    unittest.main()
