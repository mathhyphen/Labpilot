import base64
import hashlib
import hmac
import re
import time
import unittest
from unittest.mock import Mock, patch

from labpilot.notify import (
    FeishuNotifier,
    PushPlusNotifier,
    WeComNotifier,
    WxPusherNotifier,
    get_notifier,
)


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

    @patch("labpilot.notify.requests.post")
    def test_feishu_signed_payload_matches_official_hmac(self, post):
        """飞书带 secret 时，签名必须按官方算法 key=secret, msg=ts+'\\n'+secret 计算。

        参考: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
        """
        post.return_value = Mock(json=lambda: {"code": 0})
        secret = "test-secret-1234"
        notifier = FeishuNotifier({
            "notification": {
                "feishu": {
                    "webhook_url": "https://example.com/feishu",
                    "secret": secret,
                    "timeout": 3,
                }
            }
        })

        self.assertTrue(notifier.send_notification("标题", "内容"))

        _, kwargs = post.call_args
        payload = kwargs["json"]
        ts = payload["timestamp"]
        # 官方算法: key=secret, msg=ts+'\n'+secret
        expected = base64.b64encode(
            hmac.new(
                secret.encode("utf-8"),
                f"{ts}\n{secret}".encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        self.assertEqual(payload["sign"], expected)

    @patch("labpilot.notify.requests.post")
    def test_feishu_timestamp_is_milliseconds(self, post):
        """飞书要求毫秒时间戳。检验值是 13 位数字（≥ 1e12）。"""
        post.return_value = Mock(json=lambda: {"code": 0})
        secret = "s"
        notifier = FeishuNotifier({
            "notification": {
                "feishu": {
                    "webhook_url": "https://example.com/feishu",
                    "secret": secret,
                }
            }
        })

        before_ms = int(time.time() * 1000)
        notifier.send_notification("t", "m")
        after_ms = int(time.time() * 1000)

        _, kwargs = post.call_args
        ts = int(kwargs["json"]["timestamp"])
        self.assertGreaterEqual(ts, before_ms)
        self.assertLessEqual(ts, after_ms)
        # 毫秒是 13 位数字；秒是 10 位
        self.assertRegex(str(ts), r"^\d{13}$")

    @patch("labpilot.notify.requests.post")
    def test_pushplus_sends_markdown_payload(self, post):
        """PushPlus expects token/title/content/template=markdown at /send."""
        post.return_value = Mock(json=lambda: {"code": 200, "msg": "ok"})
        notifier = PushPlusNotifier({
            "notification": {
                "pushplus": {
                    "token": "tok-123",
                    "template": "markdown",
                    "timeout": 4,
                }
            }
        })

        self.assertTrue(notifier.send_notification("标题", "**内容**"))

        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://www.pushplus.plus/send")
        self.assertEqual(kwargs["timeout"], 4)
        body = kwargs["json"]
        self.assertEqual(body["token"], "tok-123")
        self.assertEqual(body["title"], "标题")
        self.assertEqual(body["content"], "**内容**")
        self.assertEqual(body["template"], "markdown")

    @patch("labpilot.notify.requests.post")
    def test_pushplus_missing_token_fails_silently(self, post):
        """Without a token we must not POST; just return False."""
        notifier = PushPlusNotifier({"notification": {"pushplus": {}}})
        self.assertFalse(notifier.send_notification("t", "m"))
        post.assert_not_called()

    @patch("labpilot.notify.requests.post")
    def test_pushplus_treats_200_as_success(self, post):
        post.return_value = Mock(json=lambda: {"code": 200, "data": "id"})
        notifier = PushPlusNotifier({
            "notification": {"pushplus": {"token": "t"}}
        })
        self.assertTrue(notifier.send_notification("t", "m"))

    @patch("labpilot.notify.requests.post")
    def test_pushplus_treats_non_200_as_failure(self, post):
        post.return_value = Mock(json=lambda: {"code": 903, "msg": "limit"})
        notifier = PushPlusNotifier({
            "notification": {"pushplus": {"token": "t"}}
        })
        self.assertFalse(notifier.send_notification("t", "m"))

    @patch("labpilot.notify.requests.post")
    def test_wxpusher_sends_html_payload(self, post):
        """WxPusher expects appToken/uid/content at /api/send/message."""
        post.return_value = Mock(json=lambda: {"code": 1000, "msg": "处理成功"})
        notifier = WxPusherNotifier({
            "notification": {
                "wxpusher": {
                    "app_token": "at_xxx",
                    "uids": ["uid_1", "uid_2"],
                    "base_url": "https://wxp.example.com",
                    "timeout": 3,
                }
            }
        })

        self.assertTrue(notifier.send_notification("标题", "<b>内容</b>"))

        args, kwargs = post.call_args
        self.assertEqual(
            args[0], "https://wxp.example.com/api/send/message"
        )
        self.assertEqual(kwargs["timeout"], 3)
        body = kwargs["json"]
        self.assertEqual(body["appToken"], "at_xxx")
        self.assertEqual(body["uids"], ["uid_1", "uid_2"])
        self.assertEqual(body["content"], "<b>内容</b>")
        self.assertIn("标题", body["summary"])

    @patch("labpilot.notify.requests.post")
    def test_wxpusher_missing_app_token_fails_silently(self, post):
        notifier = WxPusherNotifier({"notification": {"wxpusher": {}}})
        self.assertFalse(notifier.send_notification("t", "m"))
        post.assert_not_called()

    @patch("labpilot.notify.requests.post")
    def test_wxpusher_treats_code_1000_as_success(self, post):
        post.return_value = Mock(json=lambda: {"code": 1000, "data": []})
        notifier = WxPusherNotifier({
            "notification": {
                "wxpusher": {
                    "app_token": "at",
                    "uids": ["u1"],
                }
            }
        })
        self.assertTrue(notifier.send_notification("t", "m"))

    @patch("labpilot.notify.requests.post")
    def test_wxpusher_treats_non_1000_as_failure(self, post):
        post.return_value = Mock(json=lambda: {"code": 9999, "msg": "error"})
        notifier = WxPusherNotifier({
            "notification": {
                "wxpusher": {
                    "app_token": "at",
                    "uids": ["u1"],
                }
            }
        })
        self.assertFalse(notifier.send_notification("t", "m"))

    def test_get_notifier_dispatches_pushplus_and_wxpusher(self):
        with patch("labpilot.notify._load_config_data") as load_config:
            with patch("labpilot.notify._notifier_instance", None):
                load_config.return_value = {
                    "notification": {
                        "active": ["pushplus", "wxpusher"],
                        "pushplus": {"token": "t"},
                        "wxpusher": {
                            "app_token": "at",
                            "uids": ["u1"],
                        },
                    }
                }
                notifier = get_notifier()
        self.assertEqual(len(notifier.notifiers), 2)
        kinds = {type(n).__name__ for n in notifier.notifiers}
        self.assertEqual(
            kinds, {"PushPlusNotifier", "WxPusherNotifier"}
        )


if __name__ == "__main__":
    unittest.main()
