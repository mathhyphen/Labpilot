import base64
import hashlib
import hmac
import re
import time
import unittest
from unittest.mock import Mock, patch

from labpilot.notify import (
    FeishuNotifier,
    NtfyNotifier,
    PushPlusNotifier,
    QQNotifier,
    WeComNotifier,
    WxPusherNotifier,
    get_notifier,
)


class NotificationTests(unittest.TestCase):
    @patch("labpilot.notify.requests.post")
    def test_feishu_notifier_sends_interactive_card(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"code": 0})
        notifier = FeishuNotifier(
            {
                "notification": {
                    "feishu": {
                        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                        "timeout": 3,
                    }
                }
            }
        )

        self.assertTrue(notifier.send_notification("标题", "内容"))

        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["msg_type"], "interactive")
        self.assertEqual(kwargs["json"]["card"]["header"]["title"]["content"], "标题")
        self.assertEqual(kwargs["timeout"], 3)

    @patch("labpilot.notify.requests.post")
    def test_wecom_notifier_sends_markdown_message(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"errcode": 0})
        notifier = WeComNotifier(
            {
                "notification": {
                    "wecom": {
                        "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                        "timeout": 4,
                    }
                }
            }
        )

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
        post.return_value = Mock(status_code=200, json=lambda: {"code": 0})
        secret = "test-secret-1234"
        notifier = FeishuNotifier(
            {
                "notification": {
                    "feishu": {
                        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                        "secret": secret,
                        "timeout": 3,
                    }
                }
            }
        )

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
        post.return_value = Mock(status_code=200, json=lambda: {"code": 0})
        secret = "s"
        notifier = FeishuNotifier(
            {
                "notification": {
                    "feishu": {
                        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                        "secret": secret,
                    }
                }
            }
        )

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
        post.return_value = Mock(status_code=200, json=lambda: {"code": 200, "msg": "ok"})
        notifier = PushPlusNotifier(
            {
                "notification": {
                    "pushplus": {
                        "token": "tok-123",
                        "template": "markdown",
                        "timeout": 4,
                    }
                }
            }
        )

        self.assertTrue(notifier.send_notification("标题", "**内容**"))

        args, kwargs = post.call_args
        # MUST be HTTPS (review finding C1: token-in-body over HTTP leaks
        # the PushPlus credential tied to a personal WeChat account).
        self.assertEqual(args[0], "https://www.pushplus.plus/send")
        self.assertEqual(kwargs["timeout"], 4)
        body = kwargs["json"]
        self.assertEqual(body["token"], "tok-123")
        self.assertEqual(body["title"], "标题")
        self.assertEqual(body["content"], "**内容**")
        self.assertEqual(body["template"], "markdown")

    def test_pushplus_endpoint_constant_is_https(self):
        """Regression guard for C1: the endpoint constant must stay https."""
        self.assertTrue(
            PushPlusNotifier.ENDPOINT.startswith("https://"),
            f"PushPlus endpoint must be https, got {PushPlusNotifier.ENDPOINT!r}",
        )

    @patch("labpilot.notify.requests.post")
    def test_pushplus_missing_token_fails_silently(self, post):
        """Without a token we must not POST; just return False."""
        notifier = PushPlusNotifier({"notification": {"pushplus": {}}})
        self.assertFalse(notifier.send_notification("t", "m"))
        post.assert_not_called()

    @patch("labpilot.notify.requests.post")
    def test_pushplus_treats_200_as_success(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"code": 200, "data": "id"})
        notifier = PushPlusNotifier({"notification": {"pushplus": {"token": "t"}}})
        self.assertTrue(notifier.send_notification("t", "m"))

    @patch("labpilot.notify.requests.post")
    def test_pushplus_treats_non_200_as_failure(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"code": 903, "msg": "limit"})
        notifier = PushPlusNotifier({"notification": {"pushplus": {"token": "t"}}})
        self.assertFalse(notifier.send_notification("t", "m"))

    @patch("labpilot.notify.requests.post")
    def test_wxpusher_sends_html_payload(self, post):
        """WxPusher expects appToken/uid/content at /api/send/message."""
        post.return_value = Mock(status_code=200, json=lambda: {"code": 1000, "msg": "处理成功"})
        notifier = WxPusherNotifier(
            {
                "notification": {
                    "wxpusher": {
                        "app_token": "at_xxx",
                        "uids": ["uid_1", "uid_2"],
                        "base_url": "https://wxpusher.zjiecode.com",
                        "timeout": 3,
                    }
                }
            }
        )

        self.assertTrue(notifier.send_notification("标题", "<b>内容</b>"))

        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://wxpusher.zjiecode.com/api/send/message")
        self.assertEqual(kwargs["timeout"], 3)
        body = kwargs["json"]
        self.assertEqual(body["appToken"], "at_xxx")
        self.assertEqual(body["uids"], ["uid_1", "uid_2"])
        self.assertEqual(body["content"], "<b>内容</b>")
        self.assertIn("标题", body["summary"])

    @patch("labpilot.notify.requests.post")
    def test_wxpusher_rejects_non_allowlisted_base_url(self, post):
        """Review finding H7: base_url must be https + in allowlist.

        Otherwise a config pointing at http://127.0.0.1:8500 would turn
        the notifier into an SSRF probe that also leaks app_token.
        """
        notifier = WxPusherNotifier(
            {
                "notification": {
                    "wxpusher": {
                        "app_token": "at",
                        "uids": ["u1"],
                        "base_url": "https://attacker.example.com",
                    }
                }
            }
        )
        self.assertFalse(notifier.send_notification("t", "m"))
        post.assert_not_called()

    def test_wxpusher_rejects_http_scheme(self):
        notifier = WxPusherNotifier(
            {
                "notification": {
                    "wxpusher": {
                        "app_token": "at",
                        "uids": ["u1"],
                        "base_url": "http://wxpusher.zjiecode.com",
                    }
                }
            }
        )
        with patch("labpilot.notify.requests.post") as post:
            self.assertFalse(notifier.send_notification("t", "m"))
            post.assert_not_called()

    @patch("labpilot.notify.requests.post")
    def test_wxpusher_missing_app_token_fails_silently(self, post):
        notifier = WxPusherNotifier({"notification": {"wxpusher": {}}})
        self.assertFalse(notifier.send_notification("t", "m"))
        post.assert_not_called()

    @patch("labpilot.notify.requests.post")
    def test_wxpusher_treats_code_1000_as_success(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"code": 1000, "data": []})
        notifier = WxPusherNotifier(
            {
                "notification": {
                    "wxpusher": {
                        "app_token": "at",
                        "uids": ["u1"],
                    }
                }
            }
        )
        self.assertTrue(notifier.send_notification("t", "m"))

    @patch("labpilot.notify.requests.post")
    def test_wxpusher_treats_non_1000_as_failure(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"code": 9999, "msg": "error"})
        notifier = WxPusherNotifier(
            {
                "notification": {
                    "wxpusher": {
                        "app_token": "at",
                        "uids": ["u1"],
                    }
                }
            }
        )
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
        self.assertEqual(kinds, {"PushPlusNotifier", "WxPusherNotifier"})

    # --- QQ (OneBot 11 HTTP API) ---

    @patch("labpilot.notify.requests.post")
    def test_qq_sends_bearer_token_and_user_payload(self, post):
        """QQ/OneBot: Bearer header + user_id + combined message at /send_msg."""
        post.return_value = Mock(status_code=200, json=lambda: {"status": "ok", "retcode": 0})
        notifier = QQNotifier(
            {
                "notification": {
                    "qq": {
                        "base_url": "http://127.0.0.1:5700",
                        "access_token": "tok-abc",
                        "user_id": 123456,
                        "timeout": 5,
                    }
                }
            }
        )
        self.assertTrue(notifier.send_notification("标题", "内容"))

        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://127.0.0.1:5700/send_msg")
        body = kwargs["json"]
        self.assertEqual(body["message"], "标题\n内容")
        self.assertEqual(body["user_id"], 123456)
        self.assertNotIn("group_id", body)
        self.assertFalse(body["auto_escape"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer tok-abc")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["timeout"], 5)

    @patch("labpilot.notify.requests.post")
    def test_qq_sends_group_id_and_no_token_when_absent(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"status": "ok", "retcode": 0})
        notifier = QQNotifier(
            {"notification": {"qq": {"base_url": "http://127.0.0.1:5700", "group_id": 987654}}}
        )
        self.assertTrue(notifier.send_notification("", "内容"))

        kwargs = post.call_args.kwargs
        body = kwargs["json"]
        self.assertEqual(body["group_id"], 987654)
        self.assertNotIn("user_id", body)
        # Empty title → no prefix, just the message.
        self.assertEqual(body["message"], "内容")
        self.assertNotIn("Authorization", kwargs["headers"])

    def test_qq_rejects_when_both_user_and_group_set(self):
        notifier = QQNotifier(
            {
                "notification": {
                    "qq": {
                        "base_url": "http://127.0.0.1:5700",
                        "user_id": 1,
                        "group_id": 2,
                    }
                }
            }
        )
        with patch("labpilot.notify.requests.post") as post:
            self.assertFalse(notifier.send_notification("t", "m"))
            post.assert_not_called()

    def test_qq_rejects_when_neither_user_nor_group_set(self):
        notifier = QQNotifier({"notification": {"qq": {"base_url": "http://127.0.0.1:5700"}}})
        with patch("labpilot.notify.requests.post") as post:
            self.assertFalse(notifier.send_notification("t", "m"))
            post.assert_not_called()

    def test_qq_rejects_invalid_base_url_scheme(self):
        notifier = QQNotifier(
            {"notification": {"qq": {"base_url": "ftp://127.0.0.1:5700", "user_id": 1}}}
        )
        with patch("labpilot.notify.requests.post") as post:
            self.assertFalse(notifier.send_notification("t", "m"))
            post.assert_not_called()

    def test_qq_rejects_missing_base_url(self):
        notifier = QQNotifier({"notification": {"qq": {"user_id": 1}}})
        with patch("labpilot.notify.requests.post") as post:
            self.assertFalse(notifier.send_notification("t", "m"))
            post.assert_not_called()

    @patch("labpilot.notify.requests.post")
    def test_qq_treats_non_ok_status_as_failure(self, post):
        """success_check requires status=='ok' and retcode==0."""
        post.return_value = Mock(
            status_code=200,
            json=lambda: {"status": "failed", "retcode": 1000, "msg": "denied"},
        )
        notifier = QQNotifier(
            {"notification": {"qq": {"base_url": "http://127.0.0.1:5700", "user_id": 1}}}
        )
        self.assertFalse(notifier.send_notification("t", "m"))

    # --- ntfy ---

    @patch("labpilot.notify.requests.post")
    def test_ntfy_sends_raw_body_and_succeeds_on_200(self, post):
        post.return_value = Mock(status_code=200, text="")
        notifier = NtfyNotifier(
            {
                "notification": {
                    "ntfy": {
                        "server": "https://ntfy.sh",
                        "topic": "mytopic",
                        "timeout": 4,
                    }
                }
            }
        )
        self.assertTrue(notifier.send_notification("标题", "内容", tags="t", priority="high"))

        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://ntfy.sh/mytopic")
        self.assertEqual(kwargs["data"], "内容".encode("utf-8"))
        self.assertEqual(kwargs["headers"]["Title"], "标题")
        self.assertEqual(kwargs["headers"]["Tags"], "t")
        self.assertEqual(kwargs["headers"]["Priority"], "high")
        self.assertIsNone(kwargs["auth"])
        self.assertEqual(kwargs["timeout"], 4)

    def test_ntfy_retries_on_5xx_then_succeeds(self):
        """ntfy now routes through the shared retry path: 5xx retries, 200 wins."""
        with (
            patch("labpilot.notify.requests.post") as post,
            patch("labpilot.notify.base.time.sleep") as sleep,
        ):
            post.side_effect = [
                Mock(status_code=503, text="down"),
                Mock(status_code=200, text=""),
            ]
            notifier = NtfyNotifier(
                {"notification": {"ntfy": {"server": "https://ntfy.sh", "topic": "t"}}}
            )
            self.assertTrue(notifier.send_notification("t", "m"))
        self.assertEqual(post.call_count, 2)
        self.assertEqual(sleep.call_count, 1)

    @patch("labpilot.notify.requests.post")
    def test_ntfy_sends_basic_auth_when_credentials_set(self, post):
        post.return_value = Mock(status_code=200, text="")
        notifier = NtfyNotifier(
            {
                "notification": {
                    "ntfy": {
                        "server": "https://ntfy.sh",
                        "topic": "t",
                        "username": "u",
                        "password": "p",
                    }
                }
            }
        )
        self.assertTrue(notifier.send_notification("t", "m"))
        self.assertEqual(post.call_args.kwargs["auth"], ("u", "p"))

    def test_ntfy_rejects_invalid_scheme(self):
        notifier = NtfyNotifier({"notification": {"ntfy": {"server": "ftp://x", "topic": "t"}}})
        with patch("labpilot.notify.requests.post") as post:
            self.assertFalse(notifier.send_notification("t", "m"))
            post.assert_not_called()

    def test_ntfy_rejects_missing_hostname(self):
        notifier = NtfyNotifier({"notification": {"ntfy": {"server": "https://", "topic": "t"}}})
        with patch("labpilot.notify.requests.post") as post:
            self.assertFalse(notifier.send_notification("t", "m"))
            post.assert_not_called()

    def test_ntfy_allows_http_for_self_host(self):
        """Self-hosted ntfy on localhost is commonly http, so allow it."""
        with patch("labpilot.notify.requests.post") as post:
            post.return_value = Mock(status_code=200, text="")
            notifier = NtfyNotifier(
                {"notification": {"ntfy": {"server": "http://127.0.0.1:8080", "topic": "t"}}}
            )
            self.assertTrue(notifier.send_notification("t", "m"))
            self.assertEqual(post.call_args[0][0], "http://127.0.0.1:8080/t")


if __name__ == "__main__":
    unittest.main()
