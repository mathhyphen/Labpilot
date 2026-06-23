"""Tests for the unified config loader (review finding C3).

The project grew four near-identical copies of the same YAML-loading
loop (``load_config`` in ``cli.py``, ``GitUtils._load_config`` in
``git_utils.py``, ``_load_config_data`` in ``notify.py``,
``load_labpilot_config`` in ``api/main.py``). Behaviour drifted between
them in subtle ways. This module pins the unified contract:

  * ``labpilot.config.load_config(explicit_path=None)`` returns the YAML
    dict at ``explicit_path`` if given, else the first existing file
    in the precedence order ``./.labpilot.yaml`` → ``~/.labpilot.yaml``
    → ``<pkg>/config.yaml``, else an empty dict.
  * No defaults are injected. Callers add their own defaults after
    calling. (This matches what ``cli`` and ``api`` did; ``notify``
    and ``git_utils`` had a different shape and have to be updated.)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class LoadConfigContractTests(unittest.TestCase):
    """Pin the unified ``load_config`` API."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._explicit = os.path.join(self._tmp, "explicit.yaml")
        with open(self._explicit, "w", encoding="utf-8") as f:
            f.write("custom: true\nvalue: 42\n")

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_returns_explicit_path_contents(self):
        from labpilot.config import load_config

        cfg = load_config(explicit_path=self._explicit)
        self.assertEqual(cfg, {"custom": True, "value": 42})

    def test_explicit_path_overrides_search(self):
        """Even if a config exists in cwd / home, the explicit path wins."""
        cwd_cfg = os.path.join(os.getcwd(), ".labpilot.yaml")
        existed = os.path.exists(cwd_cfg)
        with open(cwd_cfg, "w", encoding="utf-8") as f:
            f.write("cwd: true\n")
        try:
            from labpilot.config import load_config

            cfg = load_config(explicit_path=self._explicit)
            self.assertEqual(cfg, {"custom": True, "value": 42})
            self.assertNotIn("cwd", cfg)
        finally:
            if not existed:
                os.remove(cwd_cfg)

    def test_returns_empty_dict_when_no_file(self):
        """No config anywhere -> empty dict (NOT a defaults dict)."""
        from labpilot.config import load_config

        # Patch all three search paths to non-existent locations.
        with patch("os.path.exists", return_value=False):
            cfg = load_config()
        self.assertEqual(cfg, {})

    def test_returns_empty_dict_when_file_is_empty(self):
        from labpilot.config import load_config

        empty = os.path.join(self._tmp, "empty.yaml")
        with open(empty, "w", encoding="utf-8"):
            pass
        cfg = load_config(explicit_path=empty)
        self.assertEqual(cfg, {})

    def test_explicit_path_must_exist(self):
        from labpilot.config import load_config

        with self.assertRaises(FileNotFoundError):
            load_config(explicit_path=os.path.join(self._tmp, "missing.yaml"))


class LoadConfigPrecedenceTests(unittest.TestCase):
    """The 3-path search order: cwd > home > package default."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._saved_cwd = os.path.join(os.getcwd(), ".labpilot.yaml")
        self._saved_home = os.path.expanduser("~/.labpilot.yaml")
        self._existed_cwd = os.path.exists(self._saved_cwd)
        self._existed_home = os.path.exists(self._saved_home)

    def tearDown(self):
        # Restore whatever was there before the test.
        for path, existed in (
            (self._saved_cwd, self._existed_cwd),
            (self._saved_home, self._existed_home),
        ):
            if os.path.exists(path) and not existed:
                os.remove(path)
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_cwd_takes_precedence_over_home(self):
        with open(self._saved_cwd, "w", encoding="utf-8") as f:
            f.write("source: cwd\n")
        with open(self._saved_home, "w", encoding="utf-8") as f:
            f.write("source: home\n")
        try:
            from labpilot.config import load_config

            cfg = load_config()
            self.assertEqual(cfg.get("source"), "cwd")
        finally:
            for p in (self._saved_cwd, self._saved_home):
                if os.path.exists(p):
                    os.remove(p)


if __name__ == "__main__":
    unittest.main()
