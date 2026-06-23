"""End-to-end tests for the FastAPI endpoints (review finding B.4).

Previously the only API tests covered CORS plumbing and the sanitised
``/ai/token-plan`` payload. This file pins the actual behaviour of
each route:

  * /                                          (root)
  * /experiments                  (GET, POST)
  * /experiments/{id}             (GET, PUT, DELETE)
  * /experiments/stats            (GET)

Auth is configured per-test via ``LABPILOT_API_KEY``. We also drive
the lifespan to a temp Database so cwd never gets a stray
``labpilot.db``.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class _ApiEnvCase(unittest.TestCase):
    """Base: temp DB + env-var lifecycle, plus a TestClient."""

    def setUp(self):
        self._saved_db = os.environ.get("LABPILOT_DB_PATH")
        self._saved_cors = os.environ.get("LABPILOT_CORS_ORIGINS")
        self._saved_key = os.environ.get("LABPILOT_API_KEY")
        os.environ.pop("LABPILOT_CORS_ORIGINS", None)
        self._tmpdir = tempfile.mkdtemp()
        self._tmp_db = os.path.join(self._tmpdir, "endpoints.db")
        os.environ["LABPILOT_DB_PATH"] = self._tmp_db

    def tearDown(self):
        for var, saved in (
            ("LABPILOT_DB_PATH", self._saved_db),
            ("LABPILOT_CORS_ORIGINS", self._saved_cors),
            ("LABPILOT_API_KEY", self._saved_key),
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

        # Force the module to re-read the restored env on next use.
        import importlib

        from api import main as mod

        importlib.reload(mod)

    def _client(self, key: str = "") -> TestClient:
        if key:
            os.environ["LABPILOT_API_KEY"] = key
        else:
            os.environ.pop("LABPILOT_API_KEY", None)
        import importlib

        from api import main as mod

        importlib.reload(mod)
        return TestClient(mod.app)


class RootEndpointTests(_ApiEnvCase):
    def test_root_returns_welcome(self):
        client = self._client()
        with client:
            r = client.get("/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("message", body)
        self.assertEqual(body["status"], "running")


class GetExperimentsTests(_ApiEnvCase):
    def test_get_experiments_empty(self):
        client = self._client()
        with client:
            r = client.get("/experiments")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_get_experiments_returns_inserted_rows(self):
        client = self._client(key="k")
        with client:
            client.post(
                "/experiments",
                json={"command": "echo hi"},
                headers={"X-API-Key": "k"},
            )
            r = client.get("/experiments", headers={"X-API-Key": "k"})
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["command"], "echo hi")
        self.assertEqual(rows[0]["status"], "running")

    def test_get_experiments_filters_by_status(self):
        client = self._client(key="k")
        with client:
            client.post(
                "/experiments",
                json={"command": "running one"},
                headers={"X-API-Key": "k"},
            )
            client.post(
                "/experiments",
                json={"command": "to be updated"},
                headers={"X-API-Key": "k"},
            )
            # Mark the second as success via PUT
            rows = client.get("/experiments", headers={"X-API-Key": "k"}).json()
            client.put(
                f"/experiments/{rows[1]['id']}",
                json={"status": "success"},
                headers={"X-API-Key": "k"},
            )
            r = client.get(
                "/experiments?status=success",
                headers={"X-API-Key": "k"},
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["status"], "success")

    def test_get_experiments_search_term(self):
        client = self._client(key="k")
        with client:
            client.post(
                "/experiments",
                json={"command": "train resnet50"},
                headers={"X-API-Key": "k"},
            )
            client.post(
                "/experiments",
                json={"command": "train bert"},
                headers={"X-API-Key": "k"},
            )
            r = client.get(
                "/experiments?search=resnet",
                headers={"X-API-Key": "k"},
            )
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        self.assertEqual(len(rows), 1)
        self.assertIn("resnet", rows[0]["command"])


class GetExperimentByIdTests(_ApiEnvCase):
    def test_get_existing_experiment(self):
        client = self._client(key="k")
        with client:
            post = client.post(
                "/experiments",
                json={"command": "echo a"},
                headers={"X-API-Key": "k"},
            )
            new_id = post.json()["id"]
            r = client.get(f"/experiments/{new_id}", headers={"X-API-Key": "k"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], new_id)

    def test_get_missing_experiment_returns_404(self):
        client = self._client(key="k")
        with client:
            r = client.get("/experiments/9999", headers={"X-API-Key": "k"})
        self.assertEqual(r.status_code, 404)


class CreateExperimentTests(_ApiEnvCase):
    def test_create_with_minimal_payload(self):
        client = self._client(key="k")
        with client:
            r = client.post(
                "/experiments",
                json={"command": "echo minimal"},
                headers={"X-API-Key": "k"},
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["command"], "echo minimal")
        self.assertEqual(body["status"], "running")
        self.assertIsNotNone(body["start_time"])

    def test_create_with_commit_and_params(self):
        client = self._client(key="k")
        with client:
            r = client.post(
                "/experiments",
                json={
                    "command": "python train.py",
                    "commit_hash": "abc1234567",
                    "params": "--epochs 5",
                },
                headers={"X-API-Key": "k"},
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["commit_hash"], "abc1234567")
        self.assertEqual(body["params"], "--epochs 5")


class UpdateExperimentTests(_ApiEnvCase):
    def test_update_status_and_duration(self):
        client = self._client(key="k")
        with client:
            post = client.post(
                "/experiments",
                json={"command": "echo update me"},
                headers={"X-API-Key": "k"},
            )
            new_id = post.json()["id"]
            r = client.put(
                f"/experiments/{new_id}",
                json={"status": "success", "duration": 5.0},
                headers={"X-API-Key": "k"},
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["duration"], 5.0)

    def test_update_unknown_id_returns_404(self):
        client = self._client(key="k")
        with client:
            r = client.put(
                "/experiments/9999",
                json={"status": "success"},
                headers={"X-API-Key": "k"},
            )
        self.assertEqual(r.status_code, 404)

    def test_update_with_no_fields_returns_400(self):
        client = self._client(key="k")
        with client:
            post = client.post(
                "/experiments",
                json={"command": "echo empty"},
                headers={"X-API-Key": "k"},
            )
            new_id = post.json()["id"]
            r = client.put(
                f"/experiments/{new_id}",
                json={},
                headers={"X-API-Key": "k"},
            )
        self.assertEqual(r.status_code, 400)


class DeleteExperimentTests(_ApiEnvCase):
    def test_delete_existing(self):
        client = self._client(key="k")
        with client:
            post = client.post(
                "/experiments",
                json={"command": "echo delete me"},
                headers={"X-API-Key": "k"},
            )
            new_id = post.json()["id"]
            r = client.delete(f"/experiments/{new_id}", headers={"X-API-Key": "k"})
        self.assertEqual(r.status_code, 200)
        # And it's actually gone.
        with client:
            r2 = client.get(f"/experiments/{new_id}", headers={"X-API-Key": "k"})
        self.assertEqual(r2.status_code, 404)

    def test_delete_missing_returns_404(self):
        client = self._client(key="k")
        with client:
            r = client.delete("/experiments/9999", headers={"X-API-Key": "k"})
        self.assertEqual(r.status_code, 404)


class StatsEndpointTests(_ApiEnvCase):
    def test_stats_aggregates_correctly(self):
        client = self._client(key="k")
        with client:
            for cmd, status in [("a", "running"), ("b", "success"), ("c", "success")]:
                post = client.post(
                    "/experiments",
                    json={"command": cmd},
                    headers={"X-API-Key": "k"},
                )
                if status != "running":
                    client.put(
                        f"/experiments/{post.json()['id']}",
                        json={"status": status},
                        headers={"X-API-Key": "k"},
                    )
            r = client.get("/experiments/stats", headers={"X-API-Key": "k"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["total_experiments"], 3)
        self.assertEqual(body["status_counts"].get("success"), 2)
        self.assertEqual(body["status_counts"].get("running"), 1)
        self.assertIn("last_updated", body)


if __name__ == "__main__":
    unittest.main()
