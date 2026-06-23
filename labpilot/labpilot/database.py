"""
LabPilot 数据库模块
处理实验数据的存储和检索
"""

import os
import platform
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterator, List, Optional, cast

# Default busy timeout (ms) for every connection. With WAL mode the
# dashboard can read while labrun is writing, but writers still queue;
# 5s is the established "wait, don't fail fast" sweet spot.
DEFAULT_BUSY_TIMEOUT_MS = 5000


# ---------------------------------------------------------------------------
# Schema migrations (review finding M7).
#
# Each migration is a tuple of (version, description, sql). The
# runner applies every migration whose version is strictly greater
# than the version recorded in the ``schema_version`` table, in
# ascending order. New schemas are added by appending a new tuple
# here and bumping ``CURRENT_SCHEMA_VERSION``; the runner will pick
# them up automatically on the next ``Database.migrate()`` call.
#
# SQL must be idempotent or guarded by ``CREATE ... IF NOT EXISTS``;
# the runner does not retry or skip-on-error.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    sql: str


_MIGRATIONS: List[Migration] = [
    Migration(
        version=1,
        description="initial schema — experiments table",
        sql=(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                server TEXT,
                command TEXT NOT NULL,
                commit_hash TEXT,
                commit_message TEXT,
                params TEXT,
                ckpt_path TEXT,
                duration REAL,
                status TEXT,
                log_snippet TEXT,
                exit_code INTEGER
            )
            """
        ),
    ),
    Migration(
        version=2,
        description="add free-form notes column to experiments",
        # Idempotent: SQLite will error if the column already exists,
        # so the migration runner pre-checks for it.
        sql=("ALTER TABLE experiments ADD COLUMN notes TEXT"),
    ),
    Migration(
        version=3,
        description="add server_name and commit_message columns to experiments",
        # Two column-adds in one migration. SQLite only allows one
        # ADD COLUMN per ALTER statement, so we emit two statements and
        # let ``_apply_migration`` guard each one for idempotency:
        # ``commit_message`` already exists on fresh DBs created by v1
        # and only needs adding on legacy DBs that predate the column.
        sql=(
            "ALTER TABLE experiments ADD COLUMN server_name TEXT;"
            "ALTER TABLE experiments ADD COLUMN commit_message TEXT"
        ),
    ),
]


CURRENT_SCHEMA_VERSION: int = max(m.version for m in _MIGRATIONS)


@contextmanager
def _connect(db_path: str, busy_timeout_ms: int) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection in WAL mode with a busy timeout.

    Yields the connection inside a transaction; commits on success,
    rolls back on any exception, and always closes.
    """
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        # journal_mode=WAL is sticky on the DB file but cheap to set;
        # doing it on every connection makes the connection's mode
        # explicit and survives ``DELETE``-journal rollback situations.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


class Database:
    """SQLite wrapper with WAL + busy_timeout + context-managed connections.

    All public methods open a short-lived connection inside a ``with``
    block. This keeps the lifecycle tight (no leaked file handles on
    exception) and lets the dashboard read concurrently with labrun's
    write traffic.
    """

    def __init__(
        self,
        db_path: str,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        self.db_path = db_path
        self.busy_timeout_ms = busy_timeout_ms
        # Make sure the parent directory exists so connecting to a
        # fresh path on first run doesn't fail.
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

    # --- Lifecycle ----------------------------------------------------------

    def connect(self) -> "_ConnectionCtx":
        """Return a context manager yielding a configured connection."""
        return _ConnectionCtx(self.db_path, self.busy_timeout_ms)

    def current_schema_version(self) -> int:
        """Return the schema version recorded in the DB (0 if uninitialised)."""
        with self.connect() as conn:
            try:
                row = conn.execute(
                    "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
                ).fetchone()
            except sqlite3.OperationalError:
                # No schema_version table yet — pre-migration schema.
                return 0
        return int(row[0]) if row else 0

    def migrate(self) -> int:
        """Apply pending migrations and return the new schema version.

        Idempotent: a DB already at ``CURRENT_SCHEMA_VERSION`` is a
        no-op. Migrations run inside one transaction; if any
        statement fails, the whole batch rolls back and the DB is
        left at its previous version.
        """
        with self.connect() as conn:
            # Bootstrap the version table first so the runner can
            # record progress.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    description TEXT,
                    applied_at TEXT NOT NULL
                )
                """
            )
            row = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            ).fetchone()
            current = int(row[0]) if row else 0

            for migration in _MIGRATIONS:
                if migration.version <= current:
                    continue
                # Column-add migrations are not idempotent in
                # SQLite. Detect the column already present and
                # skip just that one migration's ALTER, but still
                # record the version so the runner doesn't try
                # again next time. The detection is best-effort:
                # if the SQL isn't a column-add we just execute it.
                self._apply_migration(conn, migration)
                # Record the migration. Use INSERT OR REPLACE so a
                # partial previous run that recorded the version but
                # failed mid-SQL doesn't permanently skip the
                # upgrade.
                conn.execute(
                    """
                    INSERT OR REPLACE INTO schema_version
                        (version, description, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        migration.version,
                        migration.description,
                        datetime.now().isoformat(),
                    ),
                )
            # Read the now-current version for the return value.
            row = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            ).fetchone()
            return int(row[0]) if row else 0

    def init_db(self) -> None:
        """Create the experiments table and apply pending migrations.

        Equivalent to :meth:`migrate` for a fresh DB; the method is
        kept under its original name for backwards compatibility.
        """
        self.migrate()

    @staticmethod
    def _apply_migration(conn: sqlite3.Connection, migration: Migration) -> None:
        """Apply one migration, skipping ALTER TABLE ADD COLUMN statements
        whose target column is already present (SQLite has no
        ``IF NOT EXISTS`` for column adds).

        A migration may contain several semicolon-separated statements —
        SQLite only permits one ADD COLUMN per ALTER, so multi-column
        migrations are written as multiple statements. Each statement is
        guarded independently so the migration stays idempotent even when
        some target columns already exist.
        """
        sql = migration.sql.strip()
        if not sql:
            return
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for statement in statements:
            Database._apply_statement(conn, statement)

    @staticmethod
    def _apply_statement(conn: sqlite3.Connection, statement: str) -> None:
        """Execute one SQL statement, skipping a redundant ADD COLUMN."""
        upper = statement.upper()
        if upper.startswith("ALTER TABLE") and "ADD COLUMN" in upper:
            # Parse the table name and column name to check first.
            # Format: ALTER TABLE <name> ADD COLUMN <col> <type>
            tokens = statement.split()
            try:
                table = tokens[2]
                col = tokens[tokens.index("COLUMN") + 1]
            except (IndexError, ValueError):
                conn.execute(statement)
                return
            # PRAGMA table_info is the canonical way to list columns.
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col in cols:
                # Already there — don't re-add; the version row
                # will still get recorded.
                return
        conn.execute(statement)

    # --- CRUD ---------------------------------------------------------------

    def insert_experiment(
        self,
        command: str,
        commit_hash: str = "",
        params: str = "",
        status: str = "running",
        server_name: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> int:
        """插入一条实验记录，返回新行 id。

        Args:
            command: 实际执行的命令字符串。
            commit_hash: 运行开始时的 Git commit hash。
            params: 展平后的命令行参数字符串。
            status: 初始状态，默认 ``"running"``。
            server_name: 运行实验的主机名。为 ``None`` 时回退到
                :func:`platform.node`（跨平台——``os.uname`` 在
                Windows 上不存在）。同时写入旧的 ``server`` 列与新的
                ``server_name`` 列，保证既有统计查询继续可用。
            commit_message: 运行开始时的 Git commit message。
                ``None`` 时该列留空（NULL）。

        Returns:
            新插入行的 id。

        Raises:
            sqlite3.Error: 数据库写入失败时抛出。
        """
        with self.connect() as conn:
            start_time = datetime.now().isoformat()
            resolved_server = server_name if server_name else (platform.node() or "unknown")
            cursor = conn.execute(
                """
                INSERT INTO experiments
                    (start_time, server, command, commit_hash, commit_message,
                     params, status, server_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    start_time,
                    resolved_server,
                    command,
                    commit_hash,
                    commit_message,
                    params,
                    status,
                    resolved_server,
                ),
            )
            return cast(int, cursor.lastrowid)

    def update_experiment(
        self,
        experiment_id: int,
        end_time: str,
        duration: float,
        status: str,
        log_snippet: str,
        exit_code: int,
        ckpt_path: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE experiments
                SET end_time=?, duration=?, status=?, log_snippet=?,
                    exit_code=?, ckpt_path=?
                WHERE id=?
                """,
                (
                    end_time,
                    duration,
                    status,
                    log_snippet,
                    exit_code,
                    ckpt_path,
                    experiment_id,
                ),
            )

    def get_experiment(self, experiment_id: int) -> Optional[Dict]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
            return _row_to_dict(row) if row is not None else None

    def get_experiments(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[Dict]:
        with self.connect() as conn:
            query = "SELECT * FROM experiments"
            params: list = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
            query += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(query, params).fetchall()
            return [_row_to_dict(r) for r in rows]

    def get_stats(self) -> Dict:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
            status_rows = conn.execute(
                "SELECT status, COUNT(*) FROM experiments GROUP BY status"
            ).fetchall()
            server_rows = conn.execute(
                "SELECT server, COUNT(*) FROM experiments WHERE server IS NOT NULL GROUP BY server"
            ).fetchall()
            recent = conn.execute(
                "SELECT COUNT(*) FROM experiments WHERE start_time >= datetime('now', '-1 day')"
            ).fetchone()[0]
        return {
            "total_experiments": total,
            "status_counts": {r[0]: r[1] for r in status_rows},
            "server_counts": {r[0]: r[1] for r in server_rows},
            "recent_experiments": recent,
        }


class _ConnectionCtx:
    """Thin context-manager wrapper so callers can do::

        with db.connect() as conn:
            ...

    The actual PRAGMA setup lives in ``_connect`` so it can be reused.
    """

    def __init__(self, db_path: str, busy_timeout_ms: int) -> None:
        self._cm = _connect(db_path, busy_timeout_ms)

    def __enter__(self) -> sqlite3.Connection:
        return self._cm.__enter__()

    def __exit__(self, exc_type, exc, tb) -> Optional[bool]:
        return self._cm.__exit__(exc_type, exc, tb)


def _row_to_dict(row: sqlite3.Row) -> Dict:
    """Materialise a Row into a plain dict so callers don't depend on
    sqlite3.Row (which is connection-bound).

    Keyed by column name rather than positional index so columns appended
    by later migrations (``notes``, ``server_name``, …) are included
    regardless of where they sit in the table — positional indexing would
    silently mis-map them on legacy DBs whose column order differs from a
    fresh v1 schema.
    """
    return {key: row[key] for key in row.keys()}


# ---------------------------------------------------------------------------
# Backwards-compatibility shim for ``ExperimentDB``. New code should use
# :class:`Database` directly; this alias exists so legacy call sites
# (notably the CLI's bootstrap path) keep working.
# ---------------------------------------------------------------------------
class ExperimentDB(Database):
    """Deprecated alias kept for backwards compatibility.

    New code should use :class:`Database` directly. The old
    ``ExperimentDB(db_path=None)`` signature is preserved by reading the
    CLI config when ``db_path`` is omitted.

    Review finding M2: the previous implementation called ``init_db()``
    in ``__init__``, which made constructing a ``Database`` a side
    effect. The new ``Database`` class is explicit: callers decide
    when to bootstrap the schema. We keep the auto-init here only
    because historical ``ExperimentDB(...)`` call sites relied on it.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            try:
                from .cli import load_config  # local import to avoid cycle

                config = load_config()
            except Exception:
                config = {}
            db_path = config.get("database", {}).get("path", "./labpilot.db")
        super().__init__(db_path)
        # Preserve the original "init on construction" behaviour so the
        # CLI's existing flow (ExperimentDB(...) implicitly creates the
        # table) still works.
        self.init_db()


def get_db(db_path: str = "./labpilot.db") -> Database:
    """Return a fresh :class:`Database` instance.

    Review finding M2: the previous implementation cached a single
    instance in a module-level ``_db_instance`` global. The class is
    essentially a thin wrapper around a path string; the cache added
    hidden coupling without saving anything. Each call now gets a
    fresh instance — tests can construct their own without fighting
    a global cache, and callers in labrun create at most one instance
    per process so the perf impact is nil.
    """
    return Database(db_path)
