"""
LabPilot - AI 实验管理与通知中心
通过 pip 安装的 Python 包
"""

from setuptools import setup, find_packages
import os

# 读取 README 文件
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# 读取 requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="labpilot",
    version="2.0.0",
    author="LabPilot Team",
    author_email="labpilot@example.com",
    description="AI 实验管理与通知中心 - 轻量级实验跟踪工具",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/labpilot",
    packages=find_packages(),
    install_requires=requirements,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "labrun=labpilot.cli:main",
            "labpilot=labpilot.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "labpilot": ["*.yaml", "*.md", "web/templates/*.html", "web/static/*.js"],
    },
    keywords=["machine-learning", "deep-learning", "experiment-tracking", "research", "ai"],
)