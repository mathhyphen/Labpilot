"""LabPilot 通知模块

Public API:
  * :class:`BaseNotifier`     — the common ancestor of every channel.
  * :class:`MultiNotifier`    — fans out a message to several notifiers.
  * ``get_notifier(config_path=None)`` — entry point that returns the
    appropriate notifier (or :class:`MultiNotifier` for several
    channels) given the user's ``.labpilot.yaml``.
  * :data:`NOTIFIER_REGISTRY` — name → class dict. New channels are
    added by importing them in this package and appending to the
    registry (see ``registry.py``).

The package was split out of a single 660-line ``notify.py`` (review
finding M1). Each notifier now lives in its own module; the split is
purely organisational — every public name is re-exported here so
existing ``from labpilot.notify import X`` imports keep working.
"""

# Re-exported at the package level so existing tests that patch
# ``labpilot.notify.requests.post`` / ``labpilot.notify.subprocess.run``
# / ``labpilot.notify.os.path.isfile`` (from the old single-file
# module) keep resolving to the same patched name. The actual call
# sites are in the per-channel modules.
import os  # noqa: F401  (re-exported for test compatibility)
import subprocess  # noqa: F401  (re-exported for test compatibility)
from typing import Optional

import requests  # noqa: F401  (re-exported for test compatibility)

from ..config import load_config as _load_unified_config
from .base import BaseNotifier
from .dingtalk import DingTalkNotifier
from .feishu import FeishuNotifier
from .multi import MultiNotifier
from .ntfy import NtfyNotifier
from .openclaw import OpenClawCliNotifier
from .pushplus import PushPlusNotifier
from .qq import QQNotifier
from .registry import (
    NOTIFIER_ALIASES,
    NOTIFIER_REGISTRY,
    get_notifier,
    reset_singleton_for_tests,
)
from .wecom import WeComNotifier
from .wxpusher import WxPusherNotifier

# Backwards-compat: the original module exposed ``_load_config_data``
# and ``_notifier_instance`` as module-level names. The registry now
# owns the singleton; this module keeps a forwarding shim so existing
# tests (``patch("labpilot.notify._notifier_instance", None)``) keep
# working.
_notifier_instance: Optional[BaseNotifier] = None


def _load_config_data(config_path=None):
    """Backwards-compat wrapper for the unified config loader.

    Kept for callers (and tests) that still pass an explicit
    ``config_path`` argument. The original module injected a default
    ``notification: {dingtalk: {}, ntfy: {}}`` block when the config
    was empty; preserve that for compatibility.
    """
    if config_path is not None:
        config = _load_unified_config(explicit_path=config_path)
    else:
        config = _load_unified_config()
    if not config:
        config = {"notification": {"dingtalk": {}, "ntfy": {}}}
    return config


__all__ = [
    "BaseNotifier",
    "DingTalkNotifier",
    "FeishuNotifier",
    "WeComNotifier",
    "NtfyNotifier",
    "PushPlusNotifier",
    "QQNotifier",
    "WxPusherNotifier",
    "OpenClawCliNotifier",
    "MultiNotifier",
    "NOTIFIER_REGISTRY",
    "NOTIFIER_ALIASES",
    "get_notifier",
    "reset_singleton_for_tests",
]
