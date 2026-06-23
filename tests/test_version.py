"""Tests for the package __version__ (review finding H5).

Originally ``labpilot/__init__.py`` hard-coded ``__version__ = "2.0.6"``
while ``setup.py`` said ``2.1.0``. The contract:

  * ``labpilot.__version__`` is a non-empty string.
  * It is sourced from the installed package metadata (so any bump
    in ``setup.py`` is reflected on the next ``pip install -e .``).
  * It is NOT a hard-coded literal in the package source.
"""

import re
import unittest
from unittest.mock import patch


class VersionStringTests(unittest.TestCase):
    def test_version_is_a_nonempty_string(self):
        import labpilot

        self.assertIsInstance(labpilot.__version__, str)
        self.assertGreater(len(labpilot.__version__), 0)

    def test_version_looks_like_semver(self):
        import labpilot

        # Accept "X.Y.Z" or "X.Y.Z<suffix>" (PEP 440).
        self.assertRegex(
            labpilot.__version__,
            r"^\d+\.\d+\.\d+([\-+].*)?$",
            f"Version {labpilot.__version__!r} is not PEP 440-ish",
        )

    def test_version_not_hardcoded(self):
        """If the source code contains ``__version__ = "<literal>"``
        the test fails: the version must be derived from package
        metadata, not duplicated in source."""
        from pathlib import Path

        labpilot_init = Path(__import__("labpilot").__file__).parent / "__init__.py"
        text = labpilot_init.read_text(encoding="utf-8")
        # Match __version__ = "1.2.3"  (string literal) but not the
        # function-call form.
        self.assertNotRegex(
            text,
            r'__version__\s*=\s*["\']\d+\.\d+\.\d+',
            f"__init__.py still has a hard-coded __version__ literal:\n{text}",
        )

    def test_version_reads_from_metadata(self):
        """Mock importlib.metadata.version and ensure __version__
        forwards that value (no in-process caching to a literal)."""
        with patch("importlib.metadata.version", return_value="9.9.9-test"):
            # Re-import to pick up the patched lookup.
            import importlib

            import labpilot

            importlib.reload(labpilot)
            try:
                self.assertEqual(labpilot.__version__, "9.9.9-test")
            finally:
                # Restore for other tests.
                importlib.reload(labpilot)


if __name__ == "__main__":
    unittest.main()
