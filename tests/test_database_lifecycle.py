"""Tests for the SQLite lifecycle (review finding C2).

Goals:
  * Connections must be opened inside a context manager and closed even
    when the body raises.
  * Connections must set WAL journal mode and a busy_timeout so that
    concurrent labrun + dashboard traffic doesn't lock the DB.
  * Concurrent writers must not deadlock.
  * The API lifespan must initialize the DB at startup, not at import
    time, so a custom ``LABPILOT_DB_PATH`` is honored.
"""

import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


class DatabaseConnectionContextTests(unittest.TestCase):
    """The Database must yield a properly-configured connection."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._path = os.path.join(self._tmpdir, "test.db")
        from labpilot.database import Database

        self._db = Database(self._path)

    def tearDown(self):
        # Best-effort cleanup; SQLite may leave WAL/SHM files behind.
        for ext in ("", "-wal", "-shm", "-journal"):
            p = self._path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    def test_connect_yields_connection(self):
        with self._db.connect() as conn:
            self.assertIsInstance(conn, sqlite3.Connection)

    def test_connect_sets_wal_journal_mode(self):
        with self._db.connect() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

    def test_connect_sets_busy_timeout(self):
        with self._db.connect() as conn:
            ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            # busy_timeout is in milliseconds; we set it to 5000.
            self.assertGreaterEqual(ms, 1000)

    def test_exception_inside_with_closes_connection_and_rolls_back(self):
        """Raising inside ``with db.connect() as conn:`` must not leak
        the connection AND must roll back the transaction.

        We use DML (INSERT) because SQLite auto-commits DDL (``CREATE
        TABLE``) so a rollback on it would be a no-op and not actually
        exercise the rollback path.
        """
        # Bootstrap the table in its own committed transaction.
        with self._db.connect() as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")

        with self.assertRaises(RuntimeError):
            with self._db.connect() as conn:
                conn.execute("INSERT INTO t VALUES (42)")
                raise RuntimeError("simulated failure")

        # The uncommitted insert must have been rolled back.
        with self._db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
            self.assertEqual(count, 0)

        # And the next connect() must succeed — proving no file-handle
        # leak from the previous failed block.
        with self._db.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1").fetchone())

    def test_commit_persists_across_connections(self):
        with self._db.connect() as conn:
            conn.execute("CREATE TABLE t (x INT)")
            conn.execute("INSERT INTO t VALUES (42)")
        with self._db.connect() as conn:
            v = conn.execute("SELECT x FROM t").fetchone()[0]
            self.assertEqual(v, 42)


class DatabaseConcurrencyTests(unittest.TestCase):
    """WAL + busy_timeout must let concurrent writers succeed."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._path = os.path.join(self._tmpdir, "concurrent.db")
        from labpilot.database import Database

        self._db = Database(self._path)
        # Create the table once
        with self._db.connect() as conn:
            conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, n INT)")

    def tearDown(self):
        for ext in ("", "-wal", "-shm", "-journal"):
            p = self._path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    def test_ten_concurrent_writers_succeed(self):
        """Ten threads each insert a row. With WAL + busy_timeout=5000
        every write must complete (no 'database is locked' exceptions)."""
        errors: list[BaseException] = []

        def writer(n: int) -> None:
            try:
                with self._db.connect() as conn:
                    conn.execute("INSERT INTO t (n) VALUES (?)", (n,))
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertFalse(errors, f"Concurrent writes raised: {errors}")
        with self._db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        self.assertEqual(count, 10)


class DatabaseCrudTests(unittest.TestCase):
    """Full CRUD coverage for Database (review finding B.2).

    These tests pin the contract of each public method, including the
    edge cases (missing id, empty DB, filtered lists).
    """

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._path = os.path.join(self._tmpdir, "crud.db")
        from labpilot.database import Database

        self._db = Database(self._path)
        # Database.__init__ is intentionally NOT auto-initialising; the
        # caller (lifespan, CLI bootstrap, tests) decides when to
        # create the schema. Tests must do it explicitly.
        self._db.init_db()

    def tearDown(self):
        for ext in ("", "-wal", "-shm"):
            p = self._path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    def test_insert_returns_incrementing_ids(self):
        id1 = self._db.insert_experiment("cmd1", "hash1", "p1")
        id2 = self._db.insert_experiment("cmd2", "hash2", "p2")
        self.assertEqual(id2, id1 + 1)
        self.assertEqual(id1, 1)

    def test_insert_then_get_round_trip(self):
        new_id = self._db.insert_experiment("echo hi", "abc1234", "--epochs 10")
        row = self._db.get_experiment(new_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["command"], "echo hi")
        self.assertEqual(row["commit_hash"], "abc1234")
        self.assertEqual(row["params"], "--epochs 10")
        self.assertEqual(row["status"], "running")
        # server is auto-populated by insert_experiment
        self.assertIsInstance(row["server"], str)
        self.assertGreater(len(row["server"]), 0)
        # start_time is ISO-8601-ish
        self.assertRegex(row["start_time"], r"^\d{4}-\d{2}-\d{2}T")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self._db.get_experiment(9999))

    def test_insert_persists_server_name_and_commit_message(self):
        """insert_experiment must persist the passed ``server_name`` and
        ``commit_message`` (core tracking bug: previously computed then
        dropped before reaching the DB)."""
        new_id = self._db.insert_experiment(
            "echo hi",
            "abc1234",
            "--epochs 10",
            server_name="gpu-box-01",
            commit_message="feat: add layer",
        )
        row = self._db.get_experiment(new_id)
        self.assertEqual(row["server_name"], "gpu-box-01")
        self.assertEqual(row["commit_message"], "feat: add layer")
        # The legacy ``server`` column is kept in sync for stats queries.
        self.assertEqual(row["server"], "gpu-box-01")

    def test_insert_defaults_server_to_hostname_when_unset(self):
        """When ``server_name`` is None (backward-compatible default),
        the server columns fall back to ``platform.node()`` — never the
        literal ``"unknown"`` on a machine that actually has a hostname.
        This is the Windows fix: ``os.uname`` does not exist there."""
        import platform

        new_id = self._db.insert_experiment("cmd", "h", "p")
        row = self._db.get_experiment(new_id)
        expected = platform.node() or "unknown"
        self.assertEqual(row["server"], expected)
        self.assertEqual(row["server_name"], expected)

    def test_insert_defaults_commit_message_to_none(self):
        """``commit_message`` defaults to NULL when not provided, so
        existing callers that don't pass it keep working."""
        new_id = self._db.insert_experiment("cmd", "h", "p")
        row = self._db.get_experiment(new_id)
        self.assertIsNone(row["commit_message"])

    def test_update_persists_fields(self):
        new_id = self._db.insert_experiment("cmd", "h", "p")
        self._db.update_experiment(
            new_id,
            end_time="2026-06-08T10:00:00",
            duration=12.5,
            status="success",
            log_snippet="ok",
            exit_code=0,
            ckpt_path="out.pth",
        )
        row = self._db.get_experiment(new_id)
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["duration"], 12.5)
        self.assertEqual(row["exit_code"], 0)
        self.assertEqual(row["ckpt_path"], "out.pth")
        self.assertEqual(row["log_snippet"], "ok")

    def test_get_experiments_orders_newest_first(self):
        self._db.insert_experiment("first", "", "")
        # Force a clock difference by sleeping 5ms
        import time

        time.sleep(0.005)
        self._db.insert_experiment("second", "", "")
        rows = self._db.get_experiments()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["command"], "second")
        self.assertEqual(rows[1]["command"], "first")

    def test_get_experiments_filters_by_status(self):
        id1 = self._db.insert_experiment("running1", "", "", status="running")
        id2 = self._db.insert_experiment("success1", "", "", status="success")
        id3 = self._db.insert_experiment("running2", "", "", status="running")
        running = self._db.get_experiments(status="running")
        ids = {r["id"] for r in running}
        self.assertEqual(ids, {id1, id3})
        success = self._db.get_experiments(status="success")
        self.assertEqual({r["id"] for r in success}, {id2})

    def test_get_experiments_respects_limit_and_offset(self):
        for i in range(5):
            self._db.insert_experiment(f"cmd{i}", "", "")
        rows = self._db.get_experiments(limit=2, offset=1)
        self.assertEqual(len(rows), 2)

    def test_get_stats_aggregates(self):
        self._db.insert_experiment("a", "", "", status="running")
        self._db.insert_experiment("b", "", "", status="success")
        self._db.insert_experiment("c", "", "", status="success")
        s = self._db.get_stats()
        self.assertEqual(s["total_experiments"], 3)
        self.assertEqual(s["status_counts"].get("running"), 1)
        self.assertEqual(s["status_counts"].get("success"), 2)


class ApiLifespanTests(unittest.TestCase):
    """The API must initialize the DB at startup, not at import time."""

    def setUp(self):
        # Snapshot the env so we can restore it.
        self._saved_db_path = os.environ.get("LABPILOT_DB_PATH")
        self._saved_cors = os.environ.get("LABPILOT_CORS_ORIGINS")
        os.environ.pop("LABPILOT_CORS_ORIGINS", None)
        self._tmpdir = tempfile.mkdtemp()
        self._tmp_db = os.path.join(self._tmpdir, "lifespan_test.db")
        os.environ["LABPILOT_DB_PATH"] = self._tmp_db

    def tearDown(self):
        if self._saved_db_path is None:
            os.environ.pop("LABPILOT_DB_PATH", None)
        else:
            os.environ["LABPILOT_DB_PATH"] = self._saved_db_path
        if self._saved_cors is not None:
            os.environ["LABPILOT_CORS_ORIGINS"] = self._saved_cors
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
        # Reset the module so subsequent tests see a fresh state.
        import importlib

        from api import main as mod

        importlib.reload(mod)

    def test_lifespan_creates_db_at_startup_with_custom_path(self):
        """After reload, the temp DB path must be honored — not the
        default ``./labpilot.db`` in cwd."""
        import importlib

        from api import main as mod

        importlib.reload(mod)
        from fastapi.testclient import TestClient

        client = TestClient(mod.app)
        # Trigger the lifespan by entering the context.
        with client:
            pass
        # The temp DB file should now exist.
        self.assertTrue(
            os.path.exists(self._tmp_db),
            f"Expected {self._tmp_db} to be created at startup",
        )

    def test_lifespan_does_not_create_cwd_db(self):
        """A side-effect of import-time init_db() was creating
        ``./labpilot.db`` in cwd. Lifespan must NOT do that."""
        cwd_db = os.path.join(os.getcwd(), "labpilot.db")
        existed_before = os.path.exists(cwd_db)
        import importlib

        from api import main as mod

        importlib.reload(mod)
        from fastapi.testclient import TestClient

        client = TestClient(mod.app)
        with client:
            pass
        # If a labpilot.db appears in cwd, the lifespan didn't use the
        # env var and fell back to the default.
        if os.path.exists(cwd_db) and not existed_before:
            os.remove(cwd_db)
            self.fail(f"Lifespan created {cwd_db} in cwd despite LABPILOT_DB_PATH={self._tmp_db}")


if __name__ == "__main__":
    unittest.main()
