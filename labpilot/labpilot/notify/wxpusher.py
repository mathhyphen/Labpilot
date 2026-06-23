"""WxPusher 个人微信推送 (wxpusher.zjiecode.com)。"""

import logging
from urllib.parse import urlparse

from .base import BaseNotifier
from .registry import register

logger = logging.getLogger(__name__)


@register("wxpusher")
class WxPusherNotifier(BaseNotifier):
    """WxPusher 推送到个人微信 (测试号)。富文本支持。"""

    DEFAULT_BASE_URL = "https://wxpusher.zjiecode.com"
    # 白名单 — config 里 base_url 只能指向这些 host，防止被当成
    # SSRF 跳板同时泄露 app_token (review finding H7)。
    ALLOWED_BASE_HOSTS = frozenset({"wxpusher.zjiecode.com"})

    def __init__(self, config):
        super().__init__(config)
        self.wxpusher_config = self.config.get("notification", {}).get("wxpusher", {})

    def _validate_base_url(self, base_url: str) -> str:
        """Return a sanitized base URL or raise ValueError."""
        parsed = urlparse(base_url)
        if parsed.scheme != "https":
            raise ValueError(f"WxPusher base_url must use https, got scheme={parsed.scheme!r}")
        if parsed.hostname not in self.ALLOWED_BASE_HOSTS:
            raise ValueError(
                f"WxPusher base_url host {parsed.hostname!r} not in allowlist "
                f"{sorted(self.ALLOWED_BASE_HOSTS)}"
            )
        return base_url.rstrip("/")

    def send_notification(
        self, title: str, message: str, tags: str = "", priority: str = "default"
    ) -> bool:
        app_token = self.wxpusher_config.get("app_token", "")
        uids = self.wxpusher_config.get("uids", [])
        configured_base = self.wxpusher_config.get("base_url", self.DEFAULT_BASE_URL)
        timeout = self.wxpusher_config.get("timeout", 5)

        if not app_token or not uids:
            logger.error("WxPusher 配置错误：app_token 或 uids 未配置")
            return False

        try:
            base_url = self._validate_base_url(configured_base)
        except ValueError as e:
            logger.error("WxPusher 配置无效: %s", e)
            return False

        url = f"{base_url}/api/send/message"
        payload = {
            "appToken": app_token,
            "content": message,
            "summary": title,
            "contentType": 1,  # 1=HTML
            "uids": uids,
        }
        return self._post_json_notifier(
            endpoint=url,
            payload=payload,
            success_check=lambda r: r.get("code") == 1000,
            timeout=timeout,
            name="WxPusher",
        )
