"""Tests for the API key auth dependency (review finding C1).

Design:
  * If ``LABPILOT_API_KEY`` is unset, all write endpoints (POST/PUT/DELETE)
    must reject with 401 — secure default. Read endpoints (GET) stay open
    so the local dashboard keeps working without configuration.
  * If set, both reads and writes require ``X-API-Key: <key>`` to match.
  * Comparison is constant-time to avoid timing oracles.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    # Imported lazily so the test module can monkey-patch the env first.
    from api.main import app

    return TestClient(app)


class _EnvCase(unittest.TestCase):
    """Base class: snapshot LABPILOT_API_KEY + LABPILOT_DB_PATH, restore
    after each test.

    The DB path is pointed at a temp file so tests never rely on a stale
    ``./labpilot.db`` in cwd (mirrors tests/test_api_endpoints.py)."""

    def setUp(self):
        self._saved_key = os.environ.get("LABPILOT_API_KEY")
        self._saved_db = os.environ.get("LABPILOT_DB_PATH")
        self._tmpdir = tempfile.mkdtemp()
        self._tmp_db = os.path.join(self._tmpdir, "auth.db")
        os.environ["LABPILOT_DB_PATH"] = self._tmp_db

    def tearDown(self):
        for var, saved in (
            ("LABPILOT_API_KEY", self._saved_key),
            ("LABPILOT_DB_PATH", self._saved_db),
        ):
            if saved is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = saved

        for ext in ("", "-wal", "-shm"):
            p = self._tmp_db + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

        # Reload module so the read-only env helpers pick up the restored state.
        import importlib

        from api import main as mod

        importlib.reload(mod)

    def set_key(self, value: str) -> None:
        if value:
            os.environ["LABPILOT_API_KEY"] = value
        else:
            os.environ.pop("LABPILOT_API_KEY", None)


class ApiAuthEnvTests(_EnvCase):
    """The configured-key resolver must reflect the environment."""

    def test_unconfigured_key_is_empty_string(self):
        self.set_key("")
        from api import main as mod

        self.assertEqual(mod.get_configured_api_key(), "")

    def test_configured_key_read_from_env(self):
        self.set_key("secret-abc")
        from api import main as mod

        self.assertEqual(mod.get_configured_api_key(), "secret-abc")


class ApiAuthDependencyTests(_EnvCase):
    """The verify_api_key function must enforce the policy above."""

    def _dep(self):
        # ``verify_api_key`` reads the env at call time, so re-importing
        # is not required — but we still go through ``api.main`` so the
        # function under test is the one FastAPI uses.
        from api import main as mod

        return mod.verify_api_key

    def test_writes_rejected_when_key_unconfigured(self):
        self.set_key("")
        with pytest.raises(Exception) as exc:
            self._dep()(x_api_key=None, authorization=None, is_write=True)
        self.assertEqual(getattr(exc.value, "status_code", None), 401)

    def test_writes_rejected_when_key_unconfigured_even_with_header(self):
        """No key set + X-API-Key header set is still rejected (header
        value is meaningless when no server-side key is configured)."""
        self.set_key("")
        with pytest.raises(Exception) as exc:
            self._dep()(x_api_key="anything", authorization=None, is_write=True)
        self.assertEqual(getattr(exc.value, "status_code", None), 401)

    def test_writes_accepted_with_matching_x_api_key(self):
        self.set_key("secret-abc")
        # Should not raise
        self._dep()(x_api_key="secret-abc", authorization=None, is_write=True)

    def test_writes_rejected_with_wrong_x_api_key(self):
        self.set_key("secret-abc")
        with pytest.raises(Exception) as exc:
            self._dep()(x_api_key="wrong", authorization=None, is_write=True)
        self.assertEqual(getattr(exc.value, "status_code", None), 401)

    def test_writes_accepted_with_matching_bearer_token(self):
        self.set_key("secret-abc")
        self._dep()(
            x_api_key=None,
            authorization="Bearer secret-abc",
            is_write=True,
        )

    def test_writes_rejected_with_wrong_bearer_token(self):
        self.set_key("secret-abc")
        with pytest.raises(Exception) as exc:
            self._dep()(
                x_api_key=None,
                authorization="Bearer wrong",
                is_write=True,
            )
        self.assertEqual(getattr(exc.value, "status_code", None), 401)

    def test_reads_open_when_key_unconfigured(self):
        self.set_key("")
        # No exception — reads work without auth
        self._dep()(x_api_key=None, authorization=None, is_write=False)

    def test_reads_rejected_when_key_set_but_missing(self):
        self.set_key("secret-abc")
        with pytest.raises(Exception) as exc:
            self._dep()(x_api_key=None, authorization=None, is_write=False)
        self.assertEqual(getattr(exc.value, "status_code", None), 401)


class ApiAuthIntegrationTests(_EnvCase):
    """End-to-end: TestClient confirms the dependency is wired to real
    mutating endpoints."""

    def _client(self):
        import importlib

        from api import main as mod

        importlib.reload(mod)
        return TestClient(mod.app)

    def test_post_experiments_requires_key_when_unset(self):
        self.set_key("")
        client = self._client()
        with client:
            r = client.post("/experiments", json={"command": "echo hi"})
        self.assertEqual(r.status_code, 401, r.text)

    def test_post_experiments_succeeds_with_matching_key(self):
        self.set_key("integration-key")
        client = self._client()
        with client:
            r = client.post(
                "/experiments",
                json={"command": "echo hi"},
                headers={"X-API-Key": "integration-key"},
            )
        self.assertEqual(r.status_code, 200, r.text)

    def test_post_experiments_rejected_with_wrong_key(self):
        self.set_key("integration-key")
        client = self._client()
        with client:
            r = client.post(
                "/experiments",
                json={"command": "echo hi"},
                headers={"X-API-Key": "wrong"},
            )
        self.assertEqual(r.status_code, 401)

    def test_get_experiments_open_when_unset(self):
        self.set_key("")
        client = self._client()
        with client:
            r = client.get("/experiments")
        self.assertEqual(r.status_code, 200)

    def test_get_experiments_requires_key_when_set(self):
        self.set_key("integration-key")
        client = self._client()
        with client:
            r = client.get("/experiments")
        self.assertEqual(r.status_code, 401)

    def test_get_experiments_returns_200_on_fresh_db(self):
        """Regression: without the lifespan driven, GET /experiments hit a
        missing ``experiments`` table and returned 500 on a clean cwd."""
        self.set_key("")
        client = self._client()
        with client:
            r = client.get("/experiments")
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
