"""Tests for ``wait_for_gpu`` (review findings H8 + H1).

Two pieces of behaviour that the current implementation gets wrong:

  * H8: the CLI accepts ``--timeout`` but ``wait_for_gpu`` ignores
    it — if no GPU ever frees up, the loop waits forever.
  * H1: the inner ``time.sleep(30)`` is a single long sleep, so
    Ctrl+C can take up to 30 s to propagate.

These tests pin the fixed contract: a timeout bound, and sub-second
sleep granularity for prompt signal delivery.
"""

import time
import unittest
from unittest.mock import patch

from labpilot.cli import wait_for_gpu


class WaitForGpuTimeoutTests(unittest.TestCase):
    def _fake_get_free_gpus(self, sequence):
        """Return a side_effect that yields each value once, then
        keeps yielding the last value forever (so the loop must
        time out instead of progressing)."""
        it = iter(sequence)

        def _next(_min):
            try:
                return next(it)
            except StopIteration:
                return sequence[-1] if sequence else []

        return _next

    def test_returns_gpu_when_available_within_timeout(self):
        # GPU appears on the 2nd poll.
        with (
            patch(
                "labpilot.cli.get_free_gpus",
                self._fake_get_free_gpus([[], [0]]),
            ),
            patch("labpilot.cli.time.sleep") as sleep,
        ):
            chosen = wait_for_gpu("12g", timeout=60)
        self.assertEqual(chosen, 0)
        # We slept at least once between the empty poll and the GPU poll.
        self.assertGreaterEqual(sleep.call_count, 1)

    def test_returns_none_when_no_gpu_and_timeout_expires(self):
        # Never any GPU; the loop must time out.
        with (
            patch(
                "labpilot.cli.get_free_gpus",
                self._fake_get_free_gpus([[]]),
            ),
            patch("labpilot.cli.time.sleep"),
            patch("labpilot.cli.time.monotonic") as mono,
        ):
            # First call: start_epoch. Subsequent: elapsed > timeout.
            mono.side_effect = [0.0, 0.0, 999.0]
            chosen = wait_for_gpu("12g", timeout=10)
        self.assertIsNone(chosen)

    def test_zero_timeout_means_wait_forever_legacy(self):
        """``timeout=0`` is the historical "no limit" sentinel."""
        with patch(
            "labpilot.cli.get_free_gpus",
            self._fake_get_free_gpus([[0]]),
        ):
            chosen = wait_for_gpu("12g", timeout=0)
        self.assertEqual(chosen, 0)


class WaitForGpuInterruptibilityTests(unittest.TestCase):
    """The sleep granularity must be sub-second so Ctrl+C is
    delivered promptly. (H1.)"""

    def test_sleep_calls_are_short(self):
        """Each sleep call must be < 1 s. The pre-fix code slept
        for 30 s which made Ctrl+C take up to 30 s to land."""
        sleeps: list[float] = []

        def _capture(duration):
            sleeps.append(duration)
            # Return empty list of GPUs so the loop keeps spinning
            # until the (mocked) timeout fires.
            # Use a side-effect flag to break out after 3 sleeps.
            if len(sleeps) >= 3:
                raise StopIteration("break out of wait_for_gpu loop")

        with (
            patch("labpilot.cli.get_free_gpus", return_value=[]),
            patch("labpilot.cli.time.sleep", side_effect=_capture),
            patch("labpilot.cli.time.monotonic", side_effect=[0.0] * 10),
        ):
            with self.assertRaises(StopIteration):
                wait_for_gpu("12g", timeout=5)
        # Every sleep call must be < 1 s.
        for d in sleeps:
            self.assertLess(
                d,
                1.0,
                f"wait_for_gpu called time.sleep({d}); the per-sleep "
                f"duration must be sub-second so Ctrl+C propagates fast",
            )
