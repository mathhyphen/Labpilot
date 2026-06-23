"""Pytest configuration: makes the inner ``labpilot/api`` package importable.

The repo layout has the installable package one level deeper than the
test root, so ``from api.main import ...`` (used in
``test_api_config.py``) cannot resolve from a default ``pytest`` run
at the repo root. This conftest prepends the inner package directory
to ``sys.path`` before collection.
"""

import os
import sys

_INNER_PKG = os.path.join(os.path.dirname(__file__), "labpilot")
if os.path.isdir(_INNER_PKG) and _INNER_PKG not in sys.path:
    sys.path.insert(0, _INNER_PKG)
