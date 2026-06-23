"""ntfy.sh 通知器."""

import logging
from urllib.parse import urlparse

from .base import BaseNotifier
from .registry import register

logger = logging.getLogger(__name__)


@register("ntfy")
class NtfyNotifier(BaseNotifier):
    """ntfy 通知器"""

    DEFAULT_TIMEOUT = 5
    # 自托管 ntfy 常以 http 跑在 localhost，故两种 scheme 都允许。
    ALLOWED_SCHEMES = frozenset({"http", "https"})

    def __init__(self, config):
        super().__init__(config)
        self.ntfy_config = self.config.get("notification", {}).get("ntfy", {})

    def _validate_server(self, server: str) -> str:
        """Return a sanitized server base URL or raise ValueError.

        Args:
            server: Configured ntfy server URL.

        Returns:
            The server URL with any trailing slash stripped.

        Raises:
            ValueError: If the scheme is not http/https or the
                hostname is missing.
        """
        parsed = urlparse(server)
        if parsed.scheme not in self.ALLOWED_SCHEMES:
            raise ValueError(f"ntfy server scheme must be http or https, got {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError("ntfy server URL must include a hostname")
        return server.rstrip("/")

    def send_notification(
        self, title: str, message: str, tags: str = "", priority: str = "default"
    ) -> bool:
        server = self.ntfy_config.get("server", "https://ntfy.sh")
        topic = self.ntfy_config.get("topic", "")
        username = self.ntfy_config.get("username", "")
        password = self.ntfy_config.get("password", "")
        timeout = self.ntfy_config.get("timeout", self.DEFAULT_TIMEOUT)

        if not topic:
            logger.error("ntfy 配置错误：topic 未配置")
            return False

        try:
            base_url = self._validate_server(server)
        except ValueError as e:
            logger.error("ntfy 配置无效: %s", e)
            return False

        url = f"{base_url}/{topic}"
        headers = {
            "Title": title,
            "Tags": tags,
            "Priority": priority,
        }
        auth = (username, password) if username and password else None

        return self._post_raw_notifier(
            endpoint=url,
            message=message,
            headers=headers,
            timeout=timeout,
            name="ntfy",
            auth=auth,
        )
