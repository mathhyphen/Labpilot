"""Tests for cli.py helpers.

Most of cli.py is a thin wrapper around subprocess.Popen, which is hard to
test without spawning real children. We test the small helpers directly.
"""
import unittest
from unittest.mock import MagicMock

from labpilot.cli import safe_kill_process


class SafeKillProcessTests(unittest.TestCase):
    def test_swallows_process_lookup_error(self):
        """If the child already exited, kill() raises ProcessLookupError.

        This is the most common error case (race between SIGINT and
        natural exit). The helper must absorb it silently.
        """
        proc = MagicMock()
        proc.kill.side_effect = ProcessLookupError("No such process")
        safe_kill_process(proc)  # should not raise

    def test_swallows_os_error(self):
        """Generic OS-level failures from kill() must also be absorbed."""
        proc = MagicMock()
        proc.kill.side_effect = OSError("I/O error")
        safe_kill_process(proc)  # should not raise

    def test_propagates_keyboard_interrupt(self):
        """KeyboardInterrupt must NOT be swallowed.

        This is the regression the old bare ``except:`` introduced: a
        user pressing Ctrl+C a second time while we were trying to kill
        the child would be silently absorbed, making the wrapper
        unkillable. ``KeyboardInterrupt`` does NOT inherit from
        ``OSError``/``ProcessLookupError``, so a narrow except preserves
        correct behavior.
        """
        proc = MagicMock()
        proc.kill.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            safe_kill_process(proc)

    def test_propagates_system_exit(self):
        """``SystemExit`` (raised by ``sys.exit()``) must also propagate."""
        proc = MagicMock()
        proc.kill.side_effect = SystemExit(1)
        with self.assertRaises(SystemExit):
            safe_kill_process(proc)

    def test_calls_kill_on_running_process(self):
        """Happy path: kill() is invoked on a still-alive child."""
        proc = MagicMock()
        proc.poll.return_value = None
        safe_kill_process(proc)
        proc.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
