"""钉钉群聊机器人通知器."""

import base64
import hashlib
import hmac
import logging
import time
from urllib.parse import urlparse

from .base import BaseNotifier
from .registry import register

logger = logging.getLogger(__name__)


@register("dingtalk")
class DingTalkNotifier(BaseNotifier):
    """钉钉群聊机器人通知器"""

    # 白名单 — webhook_url 只能指向官方 host 且必须 https，防止被当成
    # SSRF 跳板 (与 wxpusher 一致的 host/scheme 校验)。
    ALLOWED_WEBHOOK_HOSTS = frozenset({"oapi.dingtalk.com"})

    def __init__(self, config):
        super().__init__(config)
        self.dingtalk_config = self.config.get("notification", {}).get("dingtalk", {})

    def _validate_webhook_url(self, webhook_url: str) -> str:
        """Return the webhook URL if scheme/host are allowed, else raise ValueError."""
        parsed = urlparse(webhook_url)
        if parsed.scheme != "https":
            raise ValueError(f"DingTalk webhook_url must use https, got scheme={parsed.scheme!r}")
        if parsed.hostname not in self.ALLOWED_WEBHOOK_HOSTS:
            raise ValueError(
                f"DingTalk webhook_url host {parsed.hostname!r} not in allowlist "
                f"{sorted(self.ALLOWED_WEBHOOK_HOSTS)}"
            )
        return webhook_url

    def send_notification(
        self, title: str, message: str, tags: str = "", priority: str = "default"
    ) -> bool:
        webhook_url = self.dingtalk_config.get("webhook_url", "")
        timeout = self.dingtalk_config.get("timeout", 5)
        secret = self.dingtalk_config.get("secret", "")

        if not webhook_url:
            logger.error("钉钉机器人配置错误：webhook_url 未配置")
            return False

        try:
            webhook_url = self._validate_webhook_url(webhook_url)
        except ValueError as e:
            logger.error("DingTalk 配置无效: %s", e)
            return False

        # 加签处理
        final_url = webhook_url
        if secret:
            timestamp = str(int(time.time() * 1000))
            secret_enc = secret.encode("utf-8")
            string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
            hmac_code = hmac.new(secret_enc, string_to_sign, digestmod=hashlib.sha256).digest()
            sign = base64.b64encode(hmac_code).decode("utf-8")
            sep = "&" if "?" in final_url else "?"
            final_url = f"{final_url}{sep}timestamp={timestamp}&sign={sign}"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"## {title}\n{message}",
            },
        }
        return self._post_json_notifier(
            endpoint=final_url,
            payload=payload,
            success_check=lambda r: r.get("errcode") == 0,
            timeout=timeout,
            name="DingTalk",
        )
