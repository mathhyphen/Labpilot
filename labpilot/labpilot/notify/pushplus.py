"""PushPlus 个人微信推送 (pushplus.plus)。"""

import logging

from .base import BaseNotifier
from .registry import register

logger = logging.getLogger(__name__)


@register("pushplus")
class PushPlusNotifier(BaseNotifier):
    """PushPlus 推送到个人微信 (公众号模板消息)。

    免费 200 条/天。API: https://www.pushplus.plus/doc/guide/apiGuide.html
    """

    # MUST be HTTPS — 请求体里带用户的 PushPlus token (与个人微信绑定)；
    # HTTP 会在任何共享/恶意网络上泄露该凭据 (review finding C1)。
    ENDPOINT = "https://www.pushplus.plus/send"

    def __init__(self, config):
        super().__init__(config)
        self.pushplus_config = self.config.get("notification", {}).get("pushplus", {})

    def send_notification(
        self, title: str, message: str, tags: str = "", priority: str = "default"
    ) -> bool:
        token = self.pushplus_config.get("token", "")
        template = self.pushplus_config.get("template", "markdown")
        timeout = self.pushplus_config.get("timeout", 5)

        if not token:
            logger.error("PushPlus 配置错误：token 未配置")
            return False

        payload = {
            "token": token,
            "title": title,
            "content": message,
            "template": template,
        }
        return self._post_json_notifier(
            endpoint=self.ENDPOINT,
            payload=payload,
            success_check=lambda r: r.get("code") == 200,
            timeout=timeout,
            name="PushPlus",
        )
