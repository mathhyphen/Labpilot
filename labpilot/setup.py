"""LabPilot - AI 实验管理与通知中心.

Legacy shim only. All package metadata — name, version, dependencies,
classifiers, URLs, entry points — lives in the root ``pyproject.toml``,
which is the source of truth for the ``setuptools.build_meta`` build
backend. This file is retained so legacy ``python setup.py …``
invocations still resolve; it passes no arguments and duplicates
nothing, so a version bump in ``pyproject.toml`` cannot drift out of
sync here.
"""

from setuptools import setup

# Guarded so ``import setup`` is side-effect free (keeps the module
# importable for tooling that introspects it). ``python setup.py <cmd>``
# still runs ``setup()`` with no args, letting setuptools pull every
# field from ``pyproject.toml``.
if __name__ == "__main__":
    setup()
