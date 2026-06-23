"""组合通知器，同时向多个渠道发送同一条消息。"""

from typing import List

from .base import BaseNotifier


class MultiNotifier(BaseNotifier):
    """组合通知器，支持同时发送多种通知"""

    def __init__(self, config, notifiers: List[BaseNotifier]) -> None:
        super().__init__(config)
        self.notifiers = list(notifiers)

    def send_notification(
        self,
        title: str,
        message: str,
        tags: str = "",
        priority: str = "default",
    ) -> bool:
        results = [n.send_notification(title, message, tags, priority) for n in self.notifiers]
        return any(results)
