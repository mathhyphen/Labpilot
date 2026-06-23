"""飞书自定义机器人通知器."""

import base64
import hashlib
import hmac
import logging
import time
from urllib.parse import urlparse

from .base import BaseNotifier
from .registry import register

logger = logging.getLogger(__name__)


@register("feishu", "lark")
class FeishuNotifier(BaseNotifier):
    """飞书自定义机器人通知器 (Lark 是国际版品牌)"""

    # 白名单 — webhook_url 只能指向官方 host (国内/国际版) 且必须 https，防 SSRF。
    ALLOWED_WEBHOOK_HOSTS = frozenset({"open.feishu.cn", "open.larksuite.com"})

    def __init__(self, config):
        super().__init__(config)
        self.feishu_config = self.config.get("notification", {}).get("feishu", {})

    def _validate_webhook_url(self, webhook_url: str) -> str:
        """Return the webhook URL if scheme/host are allowed, else raise ValueError."""
        parsed = urlparse(webhook_url)
        if parsed.scheme != "https":
            raise ValueError(f"Feishu webhook_url must use https, got scheme={parsed.scheme!r}")
        if parsed.hostname not in self.ALLOWED_WEBHOOK_HOSTS:
            raise ValueError(
                f"Feishu webhook_url host {parsed.hostname!r} not in allowlist "
                f"{sorted(self.ALLOWED_WEBHOOK_HOSTS)}"
            )
        return webhook_url

    def _build_payload(self, title: str, message: str) -> dict:
        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "markdown", "content": message}],
            },
        }

    def send_notification(
        self, title: str, message: str, tags: str = "", priority: str = "default"
    ) -> bool:
        webhook_url = self.feishu_config.get("webhook_url", "")
        timeout = self.feishu_config.get("timeout", 5)
        secret = self.feishu_config.get("secret", "")

        if not webhook_url:
            logger.error("飞书机器人配置错误：webhook_url 未配置")
            return False

        try:
            webhook_url = self._validate_webhook_url(webhook_url)
        except ValueError as e:
            logger.error("Feishu 配置无效: %s", e)
            return False

        payload = self._build_payload(title, message)
        if secret:
            # 官方算法: key=secret, msg=ts+'\n'+secret (毫秒时间戳)
            timestamp = str(int(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            payload["timestamp"] = timestamp
            payload["sign"] = base64.b64encode(hmac_code).decode("utf-8")

        return self._post_json_notifier(
            endpoint=webhook_url,
            payload=payload,
            success_check=lambda r: r.get("StatusCode") == 0 or r.get("code") == 0,
            timeout=timeout,
            name="Feishu",
        )
