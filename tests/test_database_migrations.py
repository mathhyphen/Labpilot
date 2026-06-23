"""Tests for the schema migration runner (review finding M7)."""

import os
import sqlite3
import tempfile
import unittest

from labpilot.database import (
    CURRENT_SCHEMA_VERSION,
    Database,
)


class MigrateTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._path = os.path.join(self._tmpdir, "migrate.db")
        self._db = Database(self._path)

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

    def test_fresh_db_reaches_current_version(self):
        self.assertEqual(self._db.current_schema_version(), 0)
        applied = self._db.migrate()
        self.assertEqual(applied, CURRENT_SCHEMA_VERSION)
        self.assertEqual(self._db.current_schema_version(), CURRENT_SCHEMA_VERSION)

    def test_migrate_is_idempotent(self):
        """Running migrate() twice must not raise and must not
        re-apply already-applied migrations."""
        self._db.migrate()
        # Second call: should be a no-op (every migration is
        # version <= current).
        applied = self._db.migrate()
        self.assertEqual(applied, CURRENT_SCHEMA_VERSION)
        self.assertEqual(self._db.current_schema_version(), CURRENT_SCHEMA_VERSION)

    def test_schema_version_table_records_history(self):
        self._db.migrate()
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT version, description FROM schema_version ORDER BY version"
            ).fetchall()
        versions = [r[0] for r in rows]
        self.assertEqual(versions, list(range(1, CURRENT_SCHEMA_VERSION + 1)))
        # Every recorded row must have a non-empty description.
        for row in rows:
            self.assertTrue(row[1])

    def test_experiments_table_usable_after_migrate(self):
        self._db.migrate()
        new_id = self._db.insert_experiment("cmd", "h", "p")
        self.assertGreater(new_id, 0)
        row = self._db.get_experiment(new_id)
        self.assertEqual(row["command"], "cmd")

    def test_legacy_db_without_schema_version_gets_migrated(self):
        """A pre-migration DB (experiments table exists but no
        schema_version) should be brought forward without losing
        data."""
        # Manually create a "v0" DB: just the experiments table, no
        # schema_version row. This simulates a DB created by a
        # LabPilot version that predates the migration system.
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                CREATE TABLE experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    server TEXT,
                    command TEXT NOT NULL,
                    commit_hash TEXT,
                    params TEXT,
                    ckpt_path TEXT,
                    duration REAL,
                    status TEXT,
                    log_snippet TEXT,
                    exit_code INTEGER
                )
                """
            )
            conn.execute(
                "INSERT INTO experiments (start_time, command) VALUES (?, ?)",
                ("2026-01-01T00:00:00", "legacy cmd"),
            )
            conn.commit()

        # Sanity: no schema_version yet.
        self.assertEqual(self._db.current_schema_version(), 0)

        # Migrate forward.
        self._db.migrate()
        self.assertEqual(self._db.current_schema_version(), CURRENT_SCHEMA_VERSION)

        # Legacy row is still there.
        rows = self._db.get_experiments()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["command"], "legacy cmd")

    def test_v3_adds_server_name_and_commit_message_columns(self):
        """Migration v3 must add ``server_name`` (new) and
        ``commit_message`` (already present on fresh DBs from v1) and
        stay idempotent when re-applied."""
        self._db.migrate()
        with self._db.connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(experiments)").fetchall()}
        self.assertIn("server_name", cols)
        self.assertIn("commit_message", cols)
        # Re-running migrate must not raise — the multi-statement ALTER
        # migration skips columns that already exist.
        self._db.migrate()

    def test_legacy_db_gets_both_v3_columns(self):
        """A pre-migration DB lacking both columns must get ``server_name``
        AND ``commit_message`` added by v3 — proving the multi-statement
        migration applies each ALTER independently rather than bailing
        after the first."""
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                CREATE TABLE experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    command TEXT NOT NULL
                )
                """
            )
            conn.commit()

        self._db.migrate()
        with self._db.connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(experiments)").fetchall()}
        self.assertIn("server_name", cols)
        self.assertIn("commit_message", cols)


class MigrationManifestTests(unittest.TestCase):
    """Pin the shape of the migration list so a future contributor
    can't accidentally add version=1 (would be skipped on legacy DBs)
    or version=0 (would be applied unconditionally)."""

    def test_versions_are_strictly_increasing(self):
        from labpilot.database import _MIGRATIONS

        versions = [m.version for m in _MIGRATIONS]
        self.assertEqual(versions, sorted(versions))
        self.assertEqual(versions, list(range(1, len(_MIGRATIONS) + 1)))

    def test_every_migration_has_a_description(self):
        from labpilot.database import _MIGRATIONS

        for m in _MIGRATIONS:
            self.assertTrue(m.description, f"Migration {m.version} has no description")
            self.assertTrue(m.sql.strip(), f"Migration {m.version} has no SQL")

    def test_current_version_matches_highest_migration(self):
        from labpilot.database import _MIGRATIONS

        self.assertEqual(CURRENT_SCHEMA_VERSION, max(m.version for m in _MIGRATIONS))


if __name__ == "__main__":
    unittest.main()
