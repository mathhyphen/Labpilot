"""
LabPilot Python 包
提供实验跟踪和管理功能
"""

__version__ = "2.0.6"
__author__ = "LabPilot Team"

# 这里可以定义包级别的常量和函数
from . import cli
from . import database
from . import notify
from . import git_utils

# 定义包的公共接口
__all__ = ["cli", "database", "notify", "git_utils"]
