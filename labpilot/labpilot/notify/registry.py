"""Registry + factory for the notification channels.

The registry is a single source of truth for ``active: [...]`` entries
in ``.labpilot.yaml``. Adding a new channel is now one line:

    from labpilot.notify.registry import NOTIFIER_REGISTRY
    from .mynewchannel import MyNewNotifier
    NOTIFIER_REGISTRY["mynewchannel"] = MyNewNotifier

The original 660-line ``notify.py`` had an in-line ``if 'dingtalk' in
active_providers: ...`` chain that needed editing in two places to
add a channel (the import AND the dispatcher). Review finding M1.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Type

from .base import BaseNotifier

# Channel name → notifier class. Tests and the factory consult this
# dict; nothing else.
NOTIFIER_REGISTRY: Dict[str, Type[BaseNotifier]] = {}

# Alternative names for the same channel. e.g. ``feishu`` is the
# official name; ``lark`` is the international brand; both should
# resolve to :class:`FeishuNotifier`.
NOTIFIER_ALIASES: Dict[str, str] = {}


def register(name: str, *aliases: str) -> "Callable[[Type[BaseNotifier]], Type[BaseNotifier]]":
    """Decorator that registers a notifier class in the registry.

    Usage::

        @register("dingtalk")
        class DingTalkNotifier(BaseNotifier):
            ...

    Optionally pass alias names that should resolve to the same class.
    """

    def _decorator(cls: Type[BaseNotifier]) -> Type[BaseNotifier]:
        NOTIFIER_REGISTRY[name] = cls
        for alias in aliases:
            NOTIFIER_ALIASES[alias] = name
        return cls

    return _decorator


def _build(config: dict, active_providers) -> List[BaseNotifier]:
    """Resolve an ``active:`` list into a list of notifier instances.

    Unknown names are silently dropped (we used to ``logger.error``
    here but the CLI logs which channel failed on the first send,
    so silent skip keeps the import-time path clean).
    """
    notifiers: List[BaseNotifier] = []
    for name in active_providers:
        canonical = NOTIFIER_ALIASES.get(name, name)
        cls = NOTIFIER_REGISTRY.get(canonical)
        if cls is None:
            continue
        notifiers.append(cls(config))
    return notifiers


# Process-wide singleton. Held on the package module (not on this
# registry submodule) so existing tests that patch
# ``labpilot.notify._notifier_instance`` keep working. The helper
# functions below proxy through the package attribute.
_singleton: Optional[BaseNotifier] = None


def _get_singleton() -> Optional[BaseNotifier]:
    import labpilot.notify as _pkg

    return getattr(_pkg, "_notifier_instance", None)


def _set_singleton(value: Optional[BaseNotifier]) -> None:
    import labpilot.notify as _pkg

    _pkg._notifier_instance = value


def get_notifier(config_path: Optional[str] = None) -> BaseNotifier:
    """Return the configured notifier.

    The first call resolves the active providers from
    ``.labpilot.yaml``; subsequent calls return the cached instance.
    Pass ``config_path`` to force re-resolution from a specific file
    on every call.

    Behavioural contract (unchanged from the original ``notify.py``):

      * No ``active:`` field → fall back to ``dingtalk`` if its
        webhook is set, then ``ntfy`` if its topic is set, else an
        empty active list.
      * ``active:`` may be a string (treated as a one-element list).
      * One channel → the bare notifier.
      * Multiple channels → :class:`MultiNotifier`.
      * Zero channels → :class:`DingTalkNotifier` with no config
        (which logs and returns False on send) — preserves historical
        behaviour.
    """
    cached = _get_singleton()
    if cached is not None and config_path is None:
        return cached

    from .dingtalk import DingTalkNotifier
    from .multi import MultiNotifier

    if config_path is not None:
        from ..config import load_config as _load_unified_config

        config = _load_unified_config(explicit_path=config_path)
    else:
        # Look up ``_load_config_data`` via attribute access (not
        # ``from . import ...``) so tests that patch
        # ``labpilot.notify._load_config_data`` see the patched value
        # when this function is called.
        import labpilot.notify as _pkg

        config = _pkg._load_config_data()

    notification_config = config.get("notification", {})

    if "active" in notification_config:
        active_providers = notification_config.get("active", [])
    else:
        if notification_config.get("dingtalk", {}).get("webhook_url"):
            active_providers = ["dingtalk"]
        elif notification_config.get("ntfy", {}).get("topic"):
            active_providers = ["ntfy"]
        else:
            active_providers = []

    if isinstance(active_providers, str):
        active_providers = [active_providers]

    notifiers = _build(config, active_providers)

    if len(notifiers) == 1:
        result: BaseNotifier = notifiers[0]
    elif len(notifiers) > 1:
        result = MultiNotifier(config, notifiers)
    else:
        # Preserve historical default: DingTalkNotifier with no
        # config so the next ``send_*`` call logs an error and
        # returns False instead of crashing.
        result = DingTalkNotifier(config)

    if config_path is None:
        _set_singleton(result)
    return result


def reset_singleton_for_tests() -> None:
    """Clear the cached singleton so the next ``get_notifier()`` call
    re-reads the config. Tests that mutate ``.labpilot.yaml`` or the
    env between cases should call this (or
    ``patch("labpilot.notify._notifier_instance", None)``)."""
    _set_singleton(None)
