"""LabPilot Python 包
提供实验跟踪和管理功能
"""

from importlib import metadata as _metadata

# Review finding H5: derive __version__ from the installed package
# metadata so any bump in ``setup.py`` / ``pyproject.toml`` is
# reflected on the next ``pip install -e .`` rather than drifting
# out of sync.
try:
    __version__ = _metadata.version("labpilot")
except _metadata.PackageNotFoundError:
    # Package is not installed (e.g. running from a source checkout
    # without ``pip install -e .``). Fall back to "0+unknown" so
    # callers that interpolate __version__ into log lines still get
    # a string.
    __version__ = "0+unknown"

__author__ = "LabPilot Team"

# 这里可以定义包级别的常量和函数
from . import cli, database, git_utils, notify

# 定义包的公共接口
__all__ = ["cli", "database", "notify", "git_utils"]
