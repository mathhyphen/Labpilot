"""Tests for api/main.py CORS configuration.

The original config hard-coded ``allow_origins=["*"]`` with
``allow_credentials=True``, which:
  1. Browsers reject (CORS spec forbids ``*`` with credentials).
  2. Is unsafe even if browsers accepted it (any origin allowed).

We expect:
  * Default (no env var) -> ``["http://localhost:8000"]``
  * ``LABPILOT_CORS_ORIGINS=...`` comma list -> parsed list
  * ``*`` -> credentials must be disabled
"""
import importlib
import os
import unittest
from unittest.mock import patch


class CorsConfigTests(unittest.TestCase):
    """Each test calls ``_get_cors_origins`` *inside* the
    ``patch.dict`` context so the mocked env var is still in effect.
    """

    def test_default_origins_is_localhost(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LABPILOT_CORS_ORIGINS", None)
            from api import main as mod
            self.assertEqual(mod._get_cors_origins(), ["http://localhost:8000"])

    def test_explicit_origins_parsed_from_csv(self):
        with patch.dict(
            os.environ,
            {"LABPILOT_CORS_ORIGINS": "http://a.example, https://b.example "},
            clear=False,
        ):
            from api import main as mod
            self.assertEqual(
                mod._get_cors_origins(),
                ["http://a.example", "https://b.example"],
            )

    def test_wildcard_disables_credentials(self):
        """``*`` + credentials is rejected by browsers and unsafe; we
        force credentials off when origins is ``*``."""
        with patch.dict(
            os.environ, {"LABPILOT_CORS_ORIGINS": "*"}, clear=False
        ):
            from api import main as mod
            self.assertEqual(mod._get_cors_origins(), ["*"])
            self.assertFalse(mod._cors_allows_credentials())

    def test_explicit_origins_allow_credentials(self):
        with patch.dict(
            os.environ,
            {"LABPILOT_CORS_ORIGINS": "http://a.example"},
            clear=False,
        ):
            from api import main as mod
            self.assertTrue(mod._cors_allows_credentials())

    def test_empty_env_falls_back_to_default(self):
        """An empty env value should not yield an empty list."""
        with patch.dict(os.environ, {"LABPILOT_CORS_ORIGINS": ""}, clear=False):
            from api import main as mod
            self.assertEqual(mod._get_cors_origins(), ["http://localhost:8000"])


if __name__ == "__main__":
    unittest.main()
