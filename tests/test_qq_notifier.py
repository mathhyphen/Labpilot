"""QQ 通知器 (OneBot 11 HTTP API) 单元测试.

完全隔离: 每个测试都 patch ``labpilot.notify.requests.post``，绝不
触碰真实网络。覆盖五条行为契约:

  1. 成功发送 (user_id + access_token) -> True; payload 含 user_id 与
     message; 配置 access_token 时带 ``Authorization: Bearer`` 头。
  2. user_id 与 group_id 均缺失 -> False, 不发起 HTTP。
  3. base_url 非法 (ftp scheme 或空 host) -> False, 不发起 HTTP。
  4. group_id 路径 -> payload 含 group_id, 不含 user_id。
  5. OneBot retcode 非零 -> False (即便 HTTP 200)。
"""

from unittest.mock import Mock, patch

import pytest

from labpilot.notify import QQNotifier


def _ok_response():
    """OneBot 11 成功响应: HTTP 200, ``{"status":"ok","retcode":0}``."""
    return Mock(status_code=200, json=lambda: {"status": "ok", "retcode": 0})


def _make_notifier(qq_config):
    """构造一个只含 ``qq`` 配置块的 QQNotifier."""
    return QQNotifier({"notification": {"qq": qq_config}})


@patch("labpilot.notify.requests.post")
def test_send_succeeds_with_user_id_and_bearer_token(post):
    """成功路径: 200 + retcode 0 -> True; payload 含 user_id/message, Bearer 头存在."""
    # Arrange
    post.return_value = _ok_response()
    notifier = _make_notifier(
        {
            "base_url": "http://127.0.0.1:5700",
            "access_token": "tok-abc",
            "user_id": 123456,
        }
    )

    # Act
    ok = notifier.send_notification("标题", "内容")

    # Assert
    assert ok is True
    args, kwargs = post.call_args
    assert args[0] == "http://127.0.0.1:5700/send_msg"
    body = kwargs["json"]
    assert body["user_id"] == 123456
    assert body["message"] == "标题\n内容"
    assert kwargs["headers"]["Authorization"] == "Bearer tok-abc"
    assert kwargs["headers"]["Content-Type"] == "application/json"


def test_missing_both_user_and_group_returns_false_without_http():
    """user_id 与 group_id 均缺失 -> False, 不发起 HTTP."""
    # Arrange
    notifier = _make_notifier({"base_url": "http://127.0.0.1:5700"})

    # Act / Assert
    with patch("labpilot.notify.requests.post") as post:
        ok = notifier.send_notification("t", "m")

    assert ok is False
    post.assert_not_called()


@pytest.mark.parametrize("bad_base_url", ["ftp://127.0.0.1:5700", "https://"])
def test_invalid_base_url_returns_false_without_http(bad_base_url):
    """非法 base_url (ftp scheme 或空 host) -> False, 不发起 HTTP."""
    # Arrange
    notifier = _make_notifier({"base_url": bad_base_url, "user_id": 1})

    # Act / Assert
    with patch("labpilot.notify.requests.post") as post:
        ok = notifier.send_notification("t", "m")

    assert ok is False
    post.assert_not_called()


@patch("labpilot.notify.requests.post")
def test_group_id_path_uses_group_id_not_user_id(post):
    """group_id 路径: payload 含 group_id, 不含 user_id."""
    # Arrange
    post.return_value = _ok_response()
    notifier = _make_notifier(
        {
            "base_url": "http://127.0.0.1:5700",
            "group_id": 987654,
        }
    )

    # Act
    ok = notifier.send_notification("标题", "内容")

    # Assert
    assert ok is True
    body = post.call_args.kwargs["json"]
    assert body["group_id"] == 987654
    assert "user_id" not in body


@patch("labpilot.notify.requests.post")
def test_nonzero_retcode_returns_false(post):
    """OneBot retcode 非零 -> False (即便 HTTP 200)."""
    # Arrange
    post.return_value = Mock(
        status_code=200,
        json=lambda: {"status": "ok", "retcode": 1000, "msg": "denied"},
    )
    notifier = _make_notifier(
        {
            "base_url": "http://127.0.0.1:5700",
            "user_id": 1,
        }
    )

    # Act
    ok = notifier.send_notification("t", "m")

    # Assert
    assert ok is False
