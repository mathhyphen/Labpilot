"""
LabPilot 通知模块
支持钉钉群聊机器人和 ntfy 通知
"""

import logging
import requests
import yaml
import os
import hmac
import hashlib
import base64
import time
import subprocess
from typing import Optional, Union

logger = logging.getLogger(__name__)


class BaseNotifier:
    """通知器基类"""
    def __init__(self, config=None):
        self.config = config or {}

    def send_notification(self, title: str, message: str, tags: str = "", priority: str = "default") -> bool:
        raise NotImplementedError

    def _post_json_notifier(
        self,
        endpoint: str,
        payload: dict,
        success_check,
        timeout: int,
        name: str,
    ) -> bool:
        """Shared HTTP POST + JSON response handling for webhook notifiers.

        Centralises:
          * structured logger output (no print)
          * raise_for_status() so 4xx/5xx surface a clear message
          * narrow exception handling that lets KeyboardInterrupt /
            SystemExit propagate
          * response-body redaction (logs ``status_code`` and a short
            error ``msg`` from the JSON, not the full payload which
            can echo credentials)
        """
        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error("%s 通知超时（>%.1fs）", name, timeout)
            return False
        except requests.exceptions.HTTPError as e:
            # Only log the status code + first 200 chars of body, never
            # the full response (which can echo the token in some APIs).
            snippet = (response.text or "")[:200]
            logger.error(
                "%s 通知 HTTP %s: %s",
                name, response.status_code, snippet,
            )
            # Make the exception string safe too: only the type name
            # and a generic message, never ``str(e)`` verbatim which
            # can include the URL with embedded credentials.
            logger.debug("%s HTTPError detail: %s", name, type(e).__name__)
            return False
        except requests.exceptions.RequestException as e:
            logger.error(
                "%s 通知网络错误: %s",
                name, type(e).__name__,
            )
            logger.debug("%s network error full: %s", name, e)
            return False

        try:
            result = response.json()
        except ValueError:
            logger.error(
                "%s 通知返回非 JSON (status=%s, body[:200]=%r)",
                name, response.status_code, (response.text or "")[:200],
            )
            return False

        if success_check(result):
            logger.info("%s 通知发送成功", name)
            return True

        # Whitelist the error field rather than dumping the whole dict.
        # PushPlus / WxPusher / Feishu all use ``msg``; DingTalk/WeCom
        # use ``errmsg``. Some return both as empty strings.
        err = result.get("msg") or result.get("errmsg") or "unknown error"
        err_code = result.get("code") or result.get("errcode")
        logger.error("%s 通知被拒: code=%s msg=%s", name, err_code, err)
        return False

    def send_start_notification(self, server: str, command: str, commit_hash: str) -> bool:
        title = "⏳ 实验开始"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}"
        return self.send_notification(title, message, "hourglass_done", "default")

    def send_success_notification(self, server: str, command: str, commit_hash: str,
                                duration: str, model_path: str = "",
                                log_snippet: str = "") -> bool:
        title = "✅ 实验成功"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}\nDuration: {duration}"

        if model_path:
            message += f"\nModel: {model_path}"

        if log_snippet:
            message += f"\nLog: {log_snippet[:100]}..."

        return self.send_notification(title, message, "white_check_mark", "default")

    def send_failure_notification(self, server: str, command: str, commit_hash: str,
                                exit_code: int, duration: str,
                                error_snippet: str = "") -> bool:
        title = "❌ 实验失败"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}\nExit code: {exit_code}\nDuration: {duration}"

        if error_snippet:
            message += f"\nError: {error_snippet[:100]}..."

        return self.send_notification(title, message, "x", "high")

    def send_abort_notification(self, server: str, command: str, commit_hash: str,
                                duration: str, log_snippet: str = "") -> bool:
        title = "🚫 实验中断"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}\nDuration: {duration}"

        if log_snippet:
            message += f"\nLog: {log_snippet[:100]}..."

        return self.send_notification(title, message, "no_entry_sign", "high")

    def send_test_notification(self) -> bool:
        title = "LabPilot Test"
        message = "This is a test notification from LabPilot"
        return self.send_notification(title, message, "test", "default")


class DingTalkNotifier(BaseNotifier):
    """钉钉群聊机器人通知器"""
    def __init__(self, config):
        super().__init__(config)
        self.dingtalk_config = self.config.get('notification', {}).get('dingtalk', {})
    
    def send_notification(self, title: str, message: str, tags: str = "", 
                         priority: str = "default") -> bool:
        webhook_url = self.dingtalk_config.get('webhook_url', '')
        timeout = self.dingtalk_config.get('timeout', 5)
        secret = self.dingtalk_config.get('secret', '')
        
        if not webhook_url:
            # 静默失败，或者在此处打印错误，但通常由上层逻辑决定是否调用
            print("[ERROR] 钉钉机器人配置错误：webhook_url 未配置")
            return False
        
        # 处理加签
        final_url = webhook_url
        if secret:
            timestamp = str(int(time.time() * 1000))
            secret_enc = secret.encode('utf-8')
            string_to_sign = f'{timestamp}\n{secret}'.encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign, digestmod=hashlib.sha256).digest()
            sign = base64.b64encode(hmac_code).decode('utf-8')
            
            if '?' in final_url:
                final_url += f'&timestamp={timestamp}&sign={sign}'
            else:
                final_url += f'?timestamp={timestamp}&sign={sign}'
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"## {title}\n{message}"
            }
        }

        return self._post_json_notifier(
            endpoint=final_url,
            payload=payload,
            success_check=lambda r: r.get("errcode") == 0,
            timeout=timeout,
            name="DingTalk",
        )


class FeishuNotifier(BaseNotifier):
    """飞书自定义机器人通知器"""
    def __init__(self, config):
        super().__init__(config)
        self.feishu_config = self.config.get('notification', {}).get('feishu', {})

    def _build_payload(self, title: str, message: str) -> dict:
        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title}
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": message
                    }
                ]
            }
        }

    def send_notification(self, title: str, message: str, tags: str = "",
                         priority: str = "default") -> bool:
        webhook_url = self.feishu_config.get('webhook_url', '')
        timeout = self.feishu_config.get('timeout', 5)
        secret = self.feishu_config.get('secret', '')

        if not webhook_url:
            logger.error("飞书机器人配置错误：webhook_url 未配置")
            return False

        payload = self._build_payload(title, message)
        if secret:
            # Feishu custom bot signing: key=secret, msg=timestamp+'\n'+secret
            # timestamp must be in milliseconds. See:
            # https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
            timestamp = str(int(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                secret.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                digestmod=hashlib.sha256
            ).digest()
            payload["timestamp"] = timestamp
            payload["sign"] = base64.b64encode(hmac_code).decode('utf-8')

        return self._post_json_notifier(
            endpoint=webhook_url,
            payload=payload,
            # Feishu returns StatusCode==0 in newer API, code==0 in older
            success_check=lambda r: r.get("StatusCode") == 0 or r.get("code") == 0,
            timeout=timeout,
            name="Feishu",
        )


class WeComNotifier(BaseNotifier):
    """企业微信/微信机器人通知器"""
    def __init__(self, config):
        super().__init__(config)
        notification_config = self.config.get('notification', {})
        self.wecom_config = notification_config.get('wecom') or notification_config.get('wechat', {})

    def send_notification(self, title: str, message: str, tags: str = "",
                         priority: str = "default") -> bool:
        webhook_url = self.wecom_config.get('webhook_url', '')
        timeout = self.wecom_config.get('timeout', 5)

        if not webhook_url:
            logger.error("企业微信机器人配置错误：webhook_url 未配置")
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"### {title}\n{message}"
            }
        }

        return self._post_json_notifier(
            endpoint=webhook_url,
            payload=payload,
            success_check=lambda r: r.get("errcode") == 0,
            timeout=timeout,
            name="WeCom",
        )


class NtfyNotifier(BaseNotifier):
    """ntfy 通知器"""
    def __init__(self, config):
        super().__init__(config)
        self.ntfy_config = self.config.get('notification', {}).get('ntfy', {})

    def send_notification(self, title: str, message: str, tags: str = "",
                         priority: str = "default") -> bool:
        server = self.ntfy_config.get('server', 'https://ntfy.sh')
        topic = self.ntfy_config.get('topic', '')
        username = self.ntfy_config.get('username', '')
        password = self.ntfy_config.get('password', '')
        timeout = self.ntfy_config.get('timeout', 5)

        if not topic:
            logger.error("ntfy 配置错误：topic 未配置")
            return False

        url = f"{server}/{topic}"
        headers = {
            "Title": title,
            "Tags": tags,
            "Priority": priority
        }

        # Markdown 处理 - ntfy 支持 Markdown，但需要简单格式化
        # 这里直接发送文本内容

        auth = None
        if username and password:
            auth = (username, password)

        try:
            response = requests.post(
                url,
                data=message.encode('utf-8'),
                headers=headers,
                auth=auth,
                timeout=timeout,
            )
            if response.status_code == 200:
                logger.info("ntfy 通知发送成功")
                return True
            logger.error(
                "ntfy 通知失败: status=%s body[:200]=%r",
                response.status_code, (response.text or "")[:200],
            )
            return False
        except requests.exceptions.Timeout:
            logger.error("ntfy 通知超时（>%.1fs）", timeout)
            return False
        except requests.exceptions.RequestException as e:
            logger.error("ntfy 通知网络错误: %s", type(e).__name__)
            logger.debug("ntfy network error full: %s", e)
            return False


class MultiNotifier(BaseNotifier):
    """组合通知器，支持同时发送多种通知"""
    def __init__(self, config, notifiers):
        super().__init__(config)
        self.notifiers = notifiers

    def send_notification(self, title: str, message: str, tags: str = "", priority: str = "default") -> bool:
        results = []
        for notifier in self.notifiers:
            results.append(notifier.send_notification(title, message, tags, priority))
        return any(results)


class PushPlusNotifier(BaseNotifier):
    """PushPlus (pushplus.plus) — 推送到个人微信（公众号模板消息）。

    Setup: 用户在 pushplus.plus 扫码关注公众号 → 拿到 token → 填到
    config.yaml。免费 200 条/天。
    API: https://www.pushplus.plus/doc/guide/apiGuide.html
    """
    # MUST be HTTPS — the request body carries the user's PushPlus token
    # bound to a personal WeChat account; an HTTP downgrade would leak
    # it on any shared / hostile network. (Review finding C1.)
    ENDPOINT = "https://www.pushplus.plus/send"

    def __init__(self, config):
        super().__init__(config)
        self.pushplus_config = self.config.get('notification', {}).get('pushplus', {})

    def send_notification(self, title: str, message: str, tags: str = "",
                         priority: str = "default") -> bool:
        token = self.pushplus_config.get('token', '')
        template = self.pushplus_config.get('template', 'markdown')
        timeout = self.pushplus_config.get('timeout', 5)

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


class WxPusherNotifier(BaseNotifier):
    """WxPusher (wxpusher.zjiecode.com) — 推送到个人微信（测试号）。富文本支持。

    Setup: 在 wxpusher.zjiecode.com 创建应用 → 拿 appToken → 用户扫码
    关注 → 把 uid 加到配置。
    """
    DEFAULT_BASE_URL = "https://wxpusher.zjiecode.com"
    # Whitelist of allowed hosts. Config can only point at one of these
    # to prevent the ``base_url`` field from being abused as an SSRF
    # vector that also leaks ``app_token``. (Review finding H7.)
    ALLOWED_BASE_HOSTS = frozenset({"wxpusher.zjiecode.com"})

    def __init__(self, config):
        super().__init__(config)
        self.wxpusher_config = self.config.get('notification', {}).get('wxpusher', {})

    def _validate_base_url(self, base_url: str) -> str:
        """Return a sanitized base URL or raise ValueError.

        We require:
          * scheme is ``https``
          * host is in the allowlist
        """
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        if parsed.scheme != "https":
            raise ValueError(
                f"WxPusher base_url must use https, got scheme={parsed.scheme!r}"
            )
        if parsed.hostname not in self.ALLOWED_BASE_HOSTS:
            raise ValueError(
                f"WxPusher base_url host {parsed.hostname!r} not in allowlist "
                f"{sorted(self.ALLOWED_BASE_HOSTS)}"
            )
        return base_url.rstrip("/")

    def send_notification(self, title: str, message: str, tags: str = "",
                         priority: str = "default") -> bool:
        app_token = self.wxpusher_config.get('app_token', '')
        uids = self.wxpusher_config.get('uids', [])
        configured_base = self.wxpusher_config.get('base_url', self.DEFAULT_BASE_URL)
        timeout = self.wxpusher_config.get('timeout', 5)

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


class OpenClawCliNotifier(BaseNotifier):
    """OpenClaw CLI 包装 — 已部署 OpenClaw + ClawBot 插件的个人微信推送。

    Setup:
      1. npm i -g openclaw@latest  (需要 Node.js 22+)
      2. 在已绑定 ClawBot 的设备上执行 openclaw channels login 完成绑定
      3. 把 user_id 填到 config.yaml
      4. (可选) 配置自定义 cli_path

    Note: 微信 ClawBot 插件目前灰度放量中（iOS 微信 ≥ 8.0.70），
    未在白名单的微信账号暂时收不到消息。
    """
    DEFAULT_CLI = "openclaw"
    DEFAULT_TIMEOUT = 10
    # Reject any cli_path whose basename does not start with "openclaw".
    # This prevents a malicious or compromised config.yaml from pointing
    # ``cli_path`` at ``rm``, ``curl``, ``powershell.exe``, etc. (Review
    # finding C2.)
    CLI_NAME_PREFIX = "openclaw"

    def __init__(self, config):
        super().__init__(config)
        self.openclaw_config = self.config.get('notification', {}).get('openclaw', {})

    def _resolve_cli(self) -> str:
        """Validate and resolve the configured cli_path.

        Raises FileNotFoundError if the binary doesn't exist; raises
        ValueError if its basename does not start with the allowed
        prefix.
        """
        import shutil
        cli_path = self.openclaw_config.get('cli_path', self.DEFAULT_CLI)
        # Resolve to an absolute path: if the user gave one, use it
        # as-is; otherwise look it up on PATH.
        resolved = cli_path if os.path.isabs(cli_path) else shutil.which(cli_path)
        if not resolved or not os.path.isfile(resolved):
            # Reject even if basename starts with "openclaw" — the
            # config may claim an executable that simply does not
            # exist on this host, which would silently fall through
            # to a different binary on PATH (or fail at exec time).
            raise FileNotFoundError(cli_path)
        basename = os.path.basename(resolved).lower()
        if not basename.startswith(self.CLI_NAME_PREFIX):
            raise ValueError(
                f"Refusing to invoke non-openclaw binary: {resolved} "
                f"(basename {basename!r} does not start with {self.CLI_NAME_PREFIX!r})"
            )
        return resolved

    @staticmethod
    def _validate_user_id(user_id: str) -> None:
        """Reject user_id values that could break CLI argument parsing.

        Disallows whitespace and leading ``-`` so a user_id of
        ``--help`` or ``--config /tmp/x`` cannot smuggle extra flags.
        """
        if not user_id:
            return
        if user_id.startswith("-"):
            raise ValueError(
                f"OpenClaw user_id must not start with '-': {user_id!r}"
            )
        if any(c.isspace() for c in user_id):
            raise ValueError(
                f"OpenClaw user_id must not contain whitespace: {user_id!r}"
            )

    def send_notification(self, title: str, message: str, tags: str = "",
                         priority: str = "default") -> bool:
        user_id = self.openclaw_config.get('user_id', '')
        timeout = self.openclaw_config.get('timeout', self.DEFAULT_TIMEOUT)
        body = f"{title}\n{message}" if title else message

        if not user_id:
            logger.error("OpenClaw 配置错误：user_id 未配置")
            return False
        try:
            self._validate_user_id(user_id)
            cli_path = self._resolve_cli()
        except (ValueError, FileNotFoundError) as e:
            logger.error("OpenClaw 配置或环境无效: %s", e)
            return False

        # `openclaw send <user> --message <text>` 风格调用。
        # 注意：openclaw CLI 语法可能在后续版本调整；调用失败时给出明确提示。
        cmd = [cli_path, "send", user_id, "--message", body]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                logger.info("OpenClaw 通知发送成功")
                return True
            # Don't echo user_id / full stderr (could contain sensitive
            # content) — just the exit code.
            logger.error("OpenClaw CLI 返回非零退出码 %s", result.returncode)
            logger.debug("OpenClaw stderr: %s", (result.stderr or "")[:200])
            return False
        except subprocess.TimeoutExpired:
            logger.error("OpenClaw CLI 调用超时（>%.1fs）", timeout)
            return False
        except OSError as e:
            # FileNotFoundError / PermissionError / OSError during exec.
            # Do NOT print str(e) verbatim — it can include the path of
            # the resolved binary, which may carry config info.
            logger.error("OpenClaw CLI 执行失败: %s", type(e).__name__)
            return False


def _load_config_data(config_path: Optional[str] = None):
    """加载配置文件数据"""
    config_paths = []
    
    if config_path:
        config_paths.append(config_path)
    
    config_paths.extend([
        os.path.join(os.getcwd(), ".labpilot.yaml"),
        os.path.expanduser("~/.labpilot.yaml"),
        os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    ])
    
    config = {}
    for path in config_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            break
            
    if not config:
        config = {
            'notification': {
                'dingtalk': {},
                'ntfy': {}
            }
        }
    return config


# 全局通知器实例
_notifier_instance = None


def get_notifier(config_path: Optional[str] = None) -> BaseNotifier:
    """获取通知器实例"""
    global _notifier_instance
    if _notifier_instance is None:
        config = _load_config_data(config_path)
        notification_config = config.get('notification', {})
        active_providers = notification_config.get('active', ['dingtalk'])
        
        # 兼容旧配置：如果没有 active 字段，检查 dingtalk webhook 是否存在
        if 'active' not in notification_config:
            if notification_config.get('dingtalk', {}).get('webhook_url'):
                active_providers = ['dingtalk']
            elif notification_config.get('ntfy', {}).get('topic'):
                active_providers = ['ntfy']
            else:
                active_providers = []

        # 如果 active 是字符串，转换为列表
        if isinstance(active_providers, str):
            active_providers = [active_providers]

        notifiers = []
        if 'dingtalk' in active_providers:
            notifiers.append(DingTalkNotifier(config))
        if 'ntfy' in active_providers:
            notifiers.append(NtfyNotifier(config))
        if 'feishu' in active_providers or 'lark' in active_providers:
            notifiers.append(FeishuNotifier(config))
        if 'wecom' in active_providers or 'wechat' in active_providers:
            notifiers.append(WeComNotifier(config))
        if 'pushplus' in active_providers:
            notifiers.append(PushPlusNotifier(config))
        if 'wxpusher' in active_providers:
            notifiers.append(WxPusherNotifier(config))
        if 'openclaw' in active_providers or 'clawbot' in active_providers:
            notifiers.append(OpenClawCliNotifier(config))
            
        if len(notifiers) == 1:
            _notifier_instance = notifiers[0]
        elif len(notifiers) > 1:
            _notifier_instance = MultiNotifier(config, notifiers)
        else:
            # 默认返回 DingTalkNotifier 以保持行为一致（即使没配置，打印错误也好）
            _notifier_instance = DingTalkNotifier(config)
            
    return _notifier_instance
