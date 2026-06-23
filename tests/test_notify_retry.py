"""Tests for webhook retry/backoff (review finding M5).

Every JSON notifier routes through ``BaseNotifier._post_json_notifier``.
That helper should retry transient network failures and 5xx, but NOT
retry 4xx (client error — the request is wrong, retrying won't help).

Behavioural contract:

  * Timeout / ConnectionError: retry up to N times (default 3) with
    exponential backoff (0.5s, 1s, 2s).
  * 4xx HTTPError: do NOT retry. (4xx means the request is malformed;
    retrying just spams the endpoint.)
  * 5xx HTTPError: retry (server-side issue, may be transient).
  * Non-JSON response / payload says failure: do NOT retry (caller
    handles "API rejected" semantics).

The test uses a small counter stub to assert call counts, plus a
fake ``time.sleep`` to keep the suite fast.
"""

import unittest
from unittest.mock import MagicMock, patch

from labpilot.notify.base import BaseNotifier


def _resp(status_code=200, body=None, raise_for_status_exc=None):
    r = MagicMock()
    r.status_code = status_code
    r.text = "" if body is None else "ok"
    r.json = MagicMock(return_value=body or {})
    if raise_for_status_exc is None:
        r.raise_for_status = MagicMock(return_value=None)
    else:
        r.raise_for_status = MagicMock(side_effect=raise_for_status_exc)
    return r


class WebhookRetryTests(unittest.TestCase):
    """The contract of ``_post_json_notifier`` under failure."""

    def _call(self, post, retries: int = 3):
        """Run the helper against the supplied mock ``post`` callable."""
        import requests

        # Make the test fast by patching time.sleep to no-op.
        with patch("labpilot.notify.base.time.sleep") as sleep:
            n = BaseNotifier._post_json_notifier(
                self=MagicMock(),
                endpoint="https://x",
                payload={},
                success_check=lambda r: True,
                timeout=5,
                name="T",
            )
        return n, sleep

    def test_success_first_try_no_retry(self):
        with patch("labpilot.notify.base.requests.post") as post:
            post.return_value = _resp(200, {"ok": 1})
            ok, sleep = self._call(post)
        self.assertTrue(ok)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_timeout_retries_then_succeeds(self):
        import requests

        with patch("labpilot.notify.base.requests.post") as post:
            post.side_effect = [
                requests.exceptions.Timeout(),
                requests.exceptions.Timeout(),
                _resp(200, {"ok": 1}),
            ]
            ok, sleep = self._call(post)
        self.assertTrue(ok)
        self.assertEqual(post.call_count, 3)
        # Backoff sleeps: 0.5, 1.0
        self.assertEqual(sleep.call_count, 2)
        delays = [c.args[0] for c in sleep.call_args_list]
        self.assertEqual(delays, [0.5, 1.0])

    def test_timeout_exhausts_retries_returns_false(self):
        import requests

        with patch("labpilot.notify.base.requests.post") as post:
            post.side_effect = requests.exceptions.Timeout()
            ok, sleep = self._call(post, retries=3)
        self.assertFalse(ok)
        # 1 initial + 2 retries = 3 calls
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_4xx_does_not_retry(self):
        import requests

        with patch("labpilot.notify.base.requests.post") as post:
            post.return_value = _resp(
                status_code=400,
                raise_for_status_exc=requests.exceptions.HTTPError(response=_resp(400, body="bad")),
            )
            ok, sleep = self._call(post)
        self.assertFalse(ok)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_5xx_does_retry(self):
        import requests

        with patch("labpilot.notify.base.requests.post") as post:
            post.side_effect = [
                _resp(
                    status_code=503,
                    raise_for_status_exc=requests.exceptions.HTTPError(
                        response=_resp(503, body="down")
                    ),
                ),
                _resp(200, {"ok": 1}),
            ]
            ok, sleep = self._call(post)
        self.assertTrue(ok)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(sleep.call_count, 1)

    def test_connection_error_retries(self):
        import requests

        with patch("labpilot.notify.base.requests.post") as post:
            post.side_effect = [
                requests.exceptions.ConnectionError(),
                _resp(200, {"ok": 1}),
            ]
            ok, _ = self._call(post)
        self.assertTrue(ok)
        self.assertEqual(post.call_count, 2)

    def test_payload_failure_does_not_retry(self):
        """If the server says ``success: false``, that's a valid
        response — don't retry, just log."""
        # Use a success_check that returns False for the rejected
        # payload (mirrors the real DingTalk-style check: code == 0
        # means success, anything else means the API rejected it).
        success = lambda r: r.get("code") == 0  # noqa: E731
        with patch("labpilot.notify.base.requests.post") as post:
            post.return_value = _resp(200, {"code": 999, "msg": "denied"})
            with patch("labpilot.notify.base.time.sleep") as sleep:
                ok = BaseNotifier._post_json_notifier(
                    self=MagicMock(),
                    endpoint="https://x",
                    payload={},
                    success_check=success,
                    timeout=5,
                    name="T",
                )
        self.assertFalse(ok)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
