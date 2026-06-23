"""Base class for all notifier channels.

Centralises:
  * structured logger output (no print)
  * ``raise_for_status()`` so 4xx/5xx surface a clear message
  * narrow exception handling that lets ``KeyboardInterrupt`` /
    ``SystemExit`` propagate
  * response-body redaction (logs ``status_code`` and a short
    error ``msg`` from the JSON, not the full payload which
    can echo credentials)
  * automatic retry with exponential backoff for transient
    failures (Timeout, ConnectionError, 5xx). 4xx is NOT retried
    because the request is malformed and retrying just spams the
    endpoint.
"""

import logging
import time
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)


# Default retry policy. ``MAX_ATTEMPTS`` is total attempts including
# the first one; ``INITIAL_BACKOFF`` is the sleep before the second
# attempt, doubling each subsequent retry.
MAX_ATTEMPTS = 3
INITIAL_BACKOFF = 0.5
BACKOFF_MULTIPLIER = 2.0


class BaseNotifier:
    """通知器基类."""

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}

    def send_notification(
        self,
        title: str,
        message: str,
        tags: str = "",
        priority: str = "default",
    ) -> bool:
        raise NotImplementedError

    def _post_json_notifier(
        self,
        endpoint: str,
        payload: dict,
        success_check: Callable[[dict], bool],
        timeout: int,
        name: str,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        initial_backoff: float = INITIAL_BACKOFF,
        extra_headers: Optional[dict] = None,
    ) -> bool:
        """Shared HTTP POST + JSON response handling for webhook notifiers.

        Retries on ``Timeout``, ``ConnectionError``, and 5xx
        responses; does NOT retry on 4xx (client error). A payload
        that returns 2xx but ``success_check`` says "rejected" is
        also not retried — that means the API explicitly refused the
        notification and resending won't change the outcome.

        ``extra_headers`` is merged on top of the default
        ``Content-Type: application/json`` header so channels that
        need an ``Authorization`` header (e.g. QQ/OneBot) can reuse
        the shared retry path.
        """
        headers = {"Content-Type": "application/json"}
        if extra_headers:
            headers = {**headers, **extra_headers}

        def judge(response) -> bool:
            try:
                result = response.json()
            except ValueError:
                logger.error(
                    "%s 通知返回非 JSON (status=%s, body[:200]=%r)",
                    name,
                    response.status_code,
                    (response.text or "")[:200],
                )
                return False
            if success_check(result):
                return True
            err = result.get("msg") or result.get("errmsg") or "unknown error"
            err_code = result.get("code") or result.get("errcode")
            logger.error("%s 通知被拒: code=%s msg=%s", name, err_code, err)
            return False

        return BaseNotifier._post_with_retry(
            endpoint=endpoint,
            post_kwargs={"json": payload, "headers": headers},
            judge=judge,
            timeout=timeout,
            name=name,
            max_attempts=max_attempts,
            initial_backoff=initial_backoff,
        )

    def _post_raw_notifier(
        self,
        endpoint: str,
        message: str,
        headers: dict,
        timeout: int,
        name: str,
        *,
        auth: Optional[tuple] = None,
        max_attempts: int = MAX_ATTEMPTS,
        initial_backoff: float = INITIAL_BACKOFF,
    ) -> bool:
        """Shared HTTP POST for notifiers that send a raw body (ntfy).

        Mirrors :meth:`_post_json_notifier` but sends ``message`` as
        UTF-8 bytes with caller-supplied ``headers`` (Title/Tags/
        Priority) and optional HTTP basic ``auth``. Success is a
        ``200`` response — ntfy returns plain text, so no JSON is
        parsed. Retry/backoff and 4xx-no-retry behaviour are identical
        to the JSON variant.
        """

        def judge(response) -> bool:
            if response.status_code == 200:
                return True
            logger.error(
                "%s 通知返回非预期状态码: %s",
                name,
                response.status_code,
            )
            return False

        return BaseNotifier._post_with_retry(
            endpoint=endpoint,
            post_kwargs={
                "data": message.encode("utf-8"),
                "headers": headers,
                "auth": auth,
            },
            judge=judge,
            timeout=timeout,
            name=name,
            max_attempts=max_attempts,
            initial_backoff=initial_backoff,
        )

    @staticmethod
    def _post_with_retry(
        endpoint: str,
        post_kwargs: dict,
        judge: Callable,
        timeout: int,
        name: str,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        initial_backoff: float = INITIAL_BACKOFF,
    ) -> bool:
        """Run ``requests.post`` with retry/backoff; delegate success to ``judge``.

        Retries ``Timeout``, ``ConnectionError`` and 5xx with
        exponential backoff; never retries 4xx or a terminal
        ``judge`` rejection. ``judge(response)`` returns True on
        success and False (after logging its own reason) on a
        terminal failure.
        """
        backoff = initial_backoff
        last_failure = ""

        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(
                    endpoint,
                    timeout=timeout,
                    **post_kwargs,
                )
            except requests.exceptions.Timeout:
                last_failure = f"timeout after {timeout}s"
                logger.warning(
                    "%s 通知超时 (attempt %d/%d)",
                    name,
                    attempt,
                    max_attempts,
                )
                BaseNotifier._sleep_before_retry(backoff, attempt, max_attempts)
                backoff *= BACKOFF_MULTIPLIER
                continue
            except requests.exceptions.ConnectionError as e:
                last_failure = f"connection error: {type(e).__name__}"
                logger.warning(
                    "%s 通知连接错误 (attempt %d/%d): %s",
                    name,
                    attempt,
                    max_attempts,
                    type(e).__name__,
                )
                BaseNotifier._sleep_before_retry(backoff, attempt, max_attempts)
                backoff *= BACKOFF_MULTIPLIER
                continue
            except requests.exceptions.RequestException as e:
                # Other transport errors (too many redirects, invalid
                # URL, etc.). Not retryable.
                logger.error(
                    "%s 通知网络错误: %s",
                    name,
                    type(e).__name__,
                )
                return False

            # HTTPError / 4xx / 5xx handling
            if response.status_code >= 500:
                last_failure = f"HTTP {response.status_code}"
                logger.warning(
                    "%s 通知 5xx (attempt %d/%d): %s",
                    name,
                    attempt,
                    max_attempts,
                    response.status_code,
                )
                BaseNotifier._sleep_before_retry(backoff, attempt, max_attempts)
                backoff *= BACKOFF_MULTIPLIER
                continue
            if response.status_code >= 400:
                # 4xx — don't retry; log and bail.
                snippet = (response.text or "")[:200]
                logger.error(
                    "%s 通知 HTTP %s: %s",
                    name,
                    response.status_code,
                    snippet,
                )
                return False

            # 2xx / 3xx — let the channel-specific judge decide.
            if judge(response):
                if attempt > 1:
                    logger.info(
                        "%s 通知发送成功 (after %d attempts)",
                        name,
                        attempt,
                    )
                else:
                    logger.info("%s 通知发送成功", name)
                return True

            # judge rejected the response — terminal, do not retry.
            return False

        # All attempts failed with retryable errors.
        logger.error(
            "%s 通知在 %d 次重试后仍失败: %s",
            name,
            max_attempts,
            last_failure or "unknown",
        )
        return False

    @staticmethod
    def _sleep_before_retry(backoff: float, attempt: int, max_attempts: int) -> None:
        """Sleep before the next retry, unless this was the last attempt."""
        if attempt < max_attempts:
            time.sleep(backoff)

    # --- Pre-baked message helpers -----------------------------------------

    def send_start_notification(self, server: str, command: str, commit_hash: str) -> bool:
        title = "⏳ 实验开始"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}"
        return self.send_notification(title, message, "hourglass_done", "default")

    def send_success_notification(
        self,
        server: str,
        command: str,
        commit_hash: str,
        duration: str,
        model_path: str = "",
        log_snippet: str = "",
    ) -> bool:
        title = "✅ 实验成功"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}\nDuration: {duration}"
        if model_path:
            message += f"\nModel: {model_path}"
        if log_snippet:
            message += f"\nLog: {log_snippet[:100]}..."
        return self.send_notification(title, message, "white_check_mark", "default")

    def send_failure_notification(
        self,
        server: str,
        command: str,
        commit_hash: str,
        exit_code: int,
        duration: str,
        error_snippet: str = "",
    ) -> bool:
        title = "❌ 实验失败"
        message = (
            f"[{server}] {command}\nCommit: {commit_hash[:7]}\n"
            f"Exit code: {exit_code}\nDuration: {duration}"
        )
        if error_snippet:
            message += f"\nError: {error_snippet[:100]}..."
        return self.send_notification(title, message, "x", "high")

    def send_abort_notification(
        self,
        server: str,
        command: str,
        commit_hash: str,
        duration: str,
        log_snippet: str = "",
    ) -> bool:
        title = "🚫 实验中断"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}\nDuration: {duration}"
        if log_snippet:
            message += f"\nLog: {log_snippet[:100]}..."
        return self.send_notification(title, message, "no_entry_sign", "high")

    def send_test_notification(self) -> bool:
        title = "LabPilot Test"
        message = "This is a test notification from LabPilot"
        return self.send_notification(title, message, "test", "default")
