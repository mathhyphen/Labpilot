"""Unified LabPilot configuration loader (review finding C3).

Replaces four near-identical copies of the same YAML-loading loop
(``cli.load_config``, ``git_utils.GitUtils._load_config``,
``notify._load_config_data``, ``api.main.load_labpilot_config``)
with a single source of truth.

Precedence order:

  1. ``explicit_path`` argument (if provided) — must exist or raise.
  2. ``./.labpilot.yaml`` (cwd)
  3. ``~/.labpilot.yaml`` (home)
  4. ``<pkg>/config.yaml`` (the package default)

Returns an empty dict when nothing is found. Callers add their own
default blocks (notification defaults, git defaults, etc.) AFTER
calling this function — that was the part that drifted between the
four originals.
"""

import os
from typing import Optional

import yaml


def _package_config_path() -> str:
    """Path to the package-shipped ``config.yaml``.

    Lives next to ``labpilot/__init__.py``; this module is inside the
    same package, so ``__file__``-relative lookup is safe.
    """
    return os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def _candidate_paths() -> list:
    """The 3 implicit search paths in precedence order."""
    return [
        os.path.join(os.getcwd(), ".labpilot.yaml"),
        os.path.expanduser("~/.labpilot.yaml"),
        _package_config_path(),
    ]


def load_config(explicit_path: Optional[str] = None) -> dict:
    """Load LabPilot configuration.

    Args:
        explicit_path: If given, load this file directly. It must
            exist; otherwise ``FileNotFoundError`` is raised. The
            explicit path is **not** merged with the 3-path search
            — it replaces it entirely.

    Returns:
        A ``dict`` (possibly empty) parsed from the first matching
        YAML file. ``yaml.safe_load`` is used, so no Python-specific
        tags are evaluated.

    Raises:
        FileNotFoundError: if ``explicit_path`` is given and the
            file does not exist.
    """
    if explicit_path is not None:
        if not os.path.exists(explicit_path):
            raise FileNotFoundError(explicit_path)
        with open(explicit_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    for path in _candidate_paths():
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


__all__ = ["load_config"]
