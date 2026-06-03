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
        return OpenClawCliNotifier({
            "notification": {
                "openclaw": {"user_id": "user-x", **cfg}
            }
        })

    @patch("labpilot.notify.subprocess.run")
    def test_calls_openclaw_send_with_user_and_message(self, run):
        """The CLI must receive the user_id and a combined title/body message."""
        run.return_value = _completed(returncode=0)
        notifier = self._notifier()

        self.assertTrue(notifier.send_notification("标题", "正文内容"))

        args, kwargs = run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "openclaw")
        self.assertEqual(cmd[1], "send")
        self.assertEqual(cmd[2], "user-x")
        self.assertIn("--message", cmd)
        msg_index = cmd.index("--message") + 1
        self.assertIn("标题", cmd[msg_index])
        self.assertIn("正文内容", cmd[msg_index])
        self.assertGreater(kwargs.get("timeout", 0), 0)

    @patch("labpilot.notify.subprocess.run")
    def test_uses_custom_cli_path(self, run):
        run.return_value = _completed(returncode=0)
        notifier = self._notifier(cli_path="/opt/openclaw/bin/openclaw")
        notifier.send_notification("t", "m")
        args, _ = run.call_args
        self.assertEqual(args[0][0], "/opt/openclaw/bin/openclaw")

    @patch("labpilot.notify.subprocess.run")
    def test_uses_configured_timeout(self, run):
        run.return_value = _completed(returncode=0)
        notifier = self._notifier(timeout=7)
        notifier.send_notification("t", "m")
        _, kwargs = run.call_args
        self.assertEqual(kwargs["timeout"], 7)

    def test_missing_user_id_returns_false_without_calling_cli(self):
        notifier = OpenClawCliNotifier({
            "notification": {"openclaw": {}}
        })
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


if __name__ == "__main__":
    unittest.main()
