"""OpenClaw CLI 包装 (Tencent ClawBot 插件, 个人微信推送)。"""

import logging
import os
import shutil
import subprocess

from .base import BaseNotifier
from .registry import register

logger = logging.getLogger(__name__)


@register("openclaw", "clawbot")
class OpenClawCliNotifier(BaseNotifier):
    """OpenClaw CLI 包装 — 已部署 OpenClaw + ClawBot 插件的个人微信推送。

    前置条件: Node.js 22+、``npm i -g openclaw@latest``、微信
    iOS >= 8.0.70 / Android >= 8.0.69。ClawBot 插件目前灰度放量。
    """

    DEFAULT_CLI = "openclaw"
    DEFAULT_TIMEOUT = 10
    # 拒绝 basename 不以 "openclaw" 开头的 cli_path — 防止 config 被
    # 改成 /bin/rm 之类后把每次 labrun 变成静默 exec (review finding C2)。
    CLI_NAME_PREFIX = "openclaw"

    def __init__(self, config):
        super().__init__(config)
        self.openclaw_config = self.config.get("notification", {}).get("openclaw", {})

    def _resolve_cli(self) -> str:
        """Validate and resolve the configured cli_path.

        Raises FileNotFoundError if the binary doesn't exist; raises
        ValueError if its basename does not start with the allowed
        prefix.

        Note: probe ``isfile`` directly (do NOT use ``os.path.isabs``
        as a "user gave a path" discriminator — on Windows, a
        POSIX-style path like ``/opt/openclaw/bin/openclaw`` is
        non-absolute even though the user clearly intended an
        explicit path).
        """
        cli_path = self.openclaw_config.get("cli_path", self.DEFAULT_CLI)
        if os.path.isfile(cli_path):
            resolved = cli_path
        else:
            resolved = shutil.which(cli_path)
        if not resolved:
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
            raise ValueError(f"OpenClaw user_id must not start with '-': {user_id!r}")
        if any(c.isspace() for c in user_id):
            raise ValueError(f"OpenClaw user_id must not contain whitespace: {user_id!r}")

    def send_notification(
        self, title: str, message: str, tags: str = "", priority: str = "default"
    ) -> bool:
        user_id = self.openclaw_config.get("user_id", "")
        timeout = self.openclaw_config.get("timeout", self.DEFAULT_TIMEOUT)
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
            logger.error("OpenClaw CLI 返回非零退出码 %s", result.returncode)
            logger.debug("OpenClaw stderr: %s", (result.stderr or "")[:200])
            return False
        except subprocess.TimeoutExpired:
            logger.error("OpenClaw CLI 调用超时（>%.1fs）", timeout)
            return False
        except OSError as e:
            # FileNotFoundError / PermissionError / OSError during
            # exec. Do NOT print str(e) verbatim — it can include the
            # path of the resolved binary, which may carry config
            # info. The exception type name alone is safe to log.
            logger.error("OpenClaw CLI 执行失败: %s", type(e).__name__)
            return False
