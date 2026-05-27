import unittest
from unittest.mock import Mock, patch

from labpilot.notify import FeishuNotifier, WeComNotifier, get_notifier


class NotificationTests(unittest.TestCase):
    @patch("labpilot.notify.requests.post")
    def test_feishu_notifier_sends_interactive_card(self, post):
        post.return_value = Mock(json=lambda: {"code": 0})
        notifier = FeishuNotifier({
            "notification": {
                "feishu": {
                    "webhook_url": "https://example.com/feishu",
                    "timeout": 3,
                }
            }
        })

        self.assertTrue(notifier.send_notification("标题", "内容"))

        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["msg_type"], "interactive")
        self.assertEqual(kwargs["json"]["card"]["header"]["title"]["content"], "标题")
        self.assertEqual(kwargs["timeout"], 3)

    @patch("labpilot.notify.requests.post")
    def test_wecom_notifier_sends_markdown_message(self, post):
        post.return_value = Mock(json=lambda: {"errcode": 0})
        notifier = WeComNotifier({
            "notification": {
                "wecom": {
                    "webhook_url": "https://example.com/wecom",
                    "timeout": 4,
                }
            }
        })

        self.assertTrue(notifier.send_notification("标题", "内容"))

        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["msgtype"], "markdown")
        self.assertIn("标题", kwargs["json"]["markdown"]["content"])
        self.assertEqual(kwargs["timeout"], 4)

    def test_get_notifier_accepts_new_provider_names(self):
        with patch("labpilot.notify._load_config_data") as load_config:
            with patch("labpilot.notify._notifier_instance", None):
                load_config.return_value = {
                    "notification": {
                        "active": ["feishu", "wecom"],
                        "feishu": {"webhook_url": "https://example.com/feishu"},
                        "wecom": {"webhook_url": "https://example.com/wecom"},
                    }
                }

                notifier = get_notifier()

        self.assertEqual(len(notifier.notifiers), 2)


if __name__ == "__main__":
    unittest.main()
