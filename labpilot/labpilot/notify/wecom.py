"""企业微信 / 微信机器人通知器."""

import logging
from urllib.parse import urlparse

from .base import BaseNotifier
from .registry import register

logger = logging.getLogger(__name__)


@register("wecom", "wechat")
class WeComNotifier(BaseNotifier):
    """企业微信/微信机器人通知器"""

    # 白名单 — webhook_url 只能指向官方 host 且必须 https，防 SSRF。
    ALLOWED_WEBHOOK_HOSTS = frozenset({"qyapi.weixin.qq.com"})

    def __init__(self, config):
        super().__init__(config)
        notification_config = self.config.get("notification", {})
        self.wecom_config = (
            notification_config.get("wecom") or notification_config.get("wechat") or {}
        )

    def _validate_webhook_url(self, webhook_url: str) -> str:
        """Return the webhook URL if scheme/host are allowed, else raise ValueError."""
        parsed = urlparse(webhook_url)
        if parsed.scheme != "https":
            raise ValueError(f"WeCom webhook_url must use https, got scheme={parsed.scheme!r}")
        if parsed.hostname not in self.ALLOWED_WEBHOOK_HOSTS:
            raise ValueError(
                f"WeCom webhook_url host {parsed.hostname!r} not in allowlist "
                f"{sorted(self.ALLOWED_WEBHOOK_HOSTS)}"
            )
        return webhook_url

    def send_notification(
        self, title: str, message: str, tags: str = "", priority: str = "default"
    ) -> bool:
        webhook_url = self.wecom_config.get("webhook_url", "")
        timeout = self.wecom_config.get("timeout", 5)

        if not webhook_url:
            logger.error("企业微信机器人配置错误：webhook_url 未配置")
            return False

        try:
            webhook_url = self._validate_webhook_url(webhook_url)
        except ValueError as e:
            logger.error("WeCom 配置无效: %s", e)
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": f"### {title}\n{message}"},
        }
        return self._post_json_notifier(
            endpoint=webhook_url,
            payload=payload,
            success_check=lambda r: r.get("errcode") == 0,
            timeout=timeout,
            name="WeCom",
        )
