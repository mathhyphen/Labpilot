"""QQ 通知器 (OneBot 11 HTTP API, 自托管机器人).

本通知器通过 OneBot 11 标准的 HTTP API 推送消息到 QQ。用户需要
自行部署一个 OneBot 11 协议实现 (例如 Lagrange.OneBot、go-cqhttp、
NapCat) 并开启 HTTP 调用服务。LabPilot 不连接任何公共 SaaS ——
``base_url`` 必须指向你自己的机器人实例，通常是本机
``http://127.0.0.1:5700``。

前置条件:
  * 一个运行中的 OneBot 11 实现，HTTP 服务已开启。
  * 若机器人开启了 ``access_token`` 校验，在 config 里填同样的
    ``access_token``，会以 ``Authorization: Bearer <token>`` 发送。
  * ``user_id`` (个人 QQ) 或 ``group_id`` (群号) 二选一。
"""

import logging
from urllib.parse import urlparse

from .base import BaseNotifier
from .registry import register

logger = logging.getLogger(__name__)


@register("qq", "onebot")
class QQNotifier(BaseNotifier):
    """QQ 通知器 — 经由自托管 OneBot 11 HTTP API 推送."""

    DEFAULT_TIMEOUT = 5
    # 自托管机器人通常是本机 http 服务，故两种 scheme 都允许。
    ALLOWED_SCHEMES = frozenset({"http", "https"})

    def __init__(self, config):
        super().__init__(config)
        self.qq_config = self.config.get("notification", {}).get("qq", {})

    def _validate_base_url(self, base_url: str) -> str:
        """Return a sanitized base URL or raise ValueError.

        Args:
            base_url: Configured OneBot HTTP base URL.

        Returns:
            The base URL with any trailing slash stripped.

        Raises:
            ValueError: If the scheme is not http/https or the
                hostname is missing.
        """
        parsed = urlparse(base_url)
        if parsed.scheme not in self.ALLOWED_SCHEMES:
            raise ValueError(f"QQ base_url scheme must be http or https, got {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError("QQ base_url must include a hostname")
        return base_url.rstrip("/")

    @staticmethod
    def _is_set(value) -> bool:
        """Treat ``None`` and empty string as "not configured"."""
        return value is not None and value != ""

    def send_notification(
        self, title: str, message: str, tags: str = "", priority: str = "default"
    ) -> bool:
        base_url = self.qq_config.get("base_url", "")
        access_token = self.qq_config.get("access_token", "")
        user_id = self.qq_config.get("user_id")
        group_id = self.qq_config.get("group_id")
        auto_escape = self.qq_config.get("auto_escape", False)
        timeout = self.qq_config.get("timeout", self.DEFAULT_TIMEOUT)

        if not base_url:
            logger.error("QQ 配置错误：base_url 未配置")
            return False

        try:
            base = self._validate_base_url(base_url)
        except ValueError as e:
            logger.error("QQ 配置无效: %s", e)
            return False

        has_user = self._is_set(user_id)
        has_group = self._is_set(group_id)
        if has_user == has_group:
            logger.error("QQ 配置错误：必须且只能设置 user_id 或 group_id 之一")
            return False

        endpoint = f"{base}/send_msg"
        payload = {
            "message": f"{title}\n{message}" if title else message,
            "auto_escape": bool(auto_escape),
        }
        if has_user:
            payload["user_id"] = int(user_id)
        else:
            payload["group_id"] = int(group_id)

        extra_headers = {"Authorization": "Bearer " + access_token} if access_token else None
        return self._post_json_notifier(
            endpoint=endpoint,
            payload=payload,
            success_check=lambda r: r.get("status") == "ok" and r.get("retcode") == 0,
            timeout=timeout,
            name="QQ",
            extra_headers=extra_headers,
        )
