import hmac
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from labpilot.config import load_config as _load_unified_config

# CORS defaults: secure-by-default. Wildcard ``*`` with credentials is
# rejected by browsers AND unsafe; we force credentials off when the
# operator opts into ``*`` and otherwise default to localhost.
DEFAULT_CORS_ORIGINS = ["http://localhost:8000"]
_CORS_WILDCARD = "*"


# ---------------------------------------------------------------------------
# API key authentication (review finding C1).
#
# Policy:
#   * ``LABPILOT_API_KEY`` env var empty / unset  -> writes always 401,
#     reads stay open so a local dashboard works without configuration.
#   * ``LABPILOT_API_KEY`` set                    -> reads AND writes both
#     require the key, accepted via either ``X-API-Key`` header or
#     ``Authorization: Bearer <key>``.
#   * Comparison is constant-time (hmac.compare_digest) to avoid leaking
#     the configured key through timing differences.
# ---------------------------------------------------------------------------
def get_configured_api_key() -> str:
    """Read ``LABPILOT_API_KEY``. Empty string means 'not configured'."""
    return os.getenv("LABPILOT_API_KEY", "")


def _extract_provided_key(
    x_api_key: Optional[str],
    authorization: Optional[str],
) -> str:
    """Pull the client-supplied key from either header. Empty if absent."""
    if x_api_key:
        return x_api_key.strip()
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    return ""


def verify_api_key(
    x_api_key: Optional[str] = None,
    authorization: Optional[str] = None,
    is_write: bool = False,
) -> None:
    """Enforce the API key policy. Raises HTTPException(401) on failure.

    The test layer calls this directly with explicit headers and the
    ``is_write`` flag; FastAPI route handlers wrap it via the
    ``_require_read_key`` / ``_require_write_key`` dependencies below.
    """
    configured = get_configured_api_key()
    provided = _extract_provided_key(x_api_key, authorization)

    # No key configured: secure default rejects writes; reads still pass
    # so the local dashboard keeps working without a key.
    if not configured:
        if is_write:
            raise HTTPException(
                status_code=401,
                detail=("API writes are disabled: set LABPILOT_API_KEY to enable them"),
            )
        return

    # Key configured: both reads and writes must present it.
    if not provided or not hmac.compare_digest(provided, configured):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )


def _require_read_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> None:
    verify_api_key(
        x_api_key=x_api_key,
        authorization=authorization,
        is_write=False,
    )


def _require_write_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> None:
    verify_api_key(
        x_api_key=x_api_key,
        authorization=authorization,
        is_write=True,
    )


def _get_cors_origins() -> List[str]:
    """Parse the ``LABPILOT_CORS_ORIGINS`` env var into a list of origins.

    Behavior:
      * Unset / empty -> ``["http://localhost:8000"]``
      * ``*`` -> ``["*"]`` (caller MUST disable credentials)
      * Otherwise -> CSV of trimmed, non-empty origins
    """
    raw = os.environ.get("LABPILOT_CORS_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    if raw == _CORS_WILDCARD:
        return [_CORS_WILDCARD]
    return [o.strip() for o in raw.split(",") if o.strip()]


def _cors_allows_credentials() -> bool:
    """Credentials are safe only when origins is an explicit allowlist."""
    return _get_cors_origins() != [_CORS_WILDCARD]


# Database configuration
DB_PATH = os.getenv("LABPILOT_DB_PATH", "./labpilot.db")


# Pydantic models
class Experiment(BaseModel):
    id: int
    start_time: str
    end_time: Optional[str] = None
    server: Optional[str] = None
    command: str
    commit_hash: Optional[str] = None
    commit_message: Optional[str] = None
    params: Optional[str] = None
    ckpt_path: Optional[str] = None
    duration: Optional[float] = None
    status: str
    log_snippet: Optional[str] = None
    exit_code: Optional[int] = None


class ExperimentCreate(BaseModel):
    command: str
    commit_hash: Optional[str] = None
    params: Optional[str] = None


class ExperimentUpdate(BaseModel):
    end_time: Optional[str] = None
    duration: Optional[float] = None
    status: Optional[str] = None
    log_snippet: Optional[str] = None
    exit_code: Optional[int] = None
    ckpt_path: Optional[str] = None


class TokenPlanConfig(BaseModel):
    provider: str
    base_url: str
    model: str
    timeout: int
    language: str
    max_diff_chars: int
    has_api_key: bool
    api_key_source: str


def _get_app_db(request: Request):
    """FastAPI dependency that yields the app's Database instance.

    The Database is set on ``app.state.db`` by the lifespan handler.
    Falling back to a per-request Database keeps the tests that bypass
    the lifespan (legacy ``TestClient(app)``) from blowing up, but
    every production path goes through the lifespan-initialized one.
    """
    db = getattr(request.app.state, "db", None)
    if db is not None:
        return db
    # Last-resort fallback for tests that don't drive the lifespan.
    from labpilot.database import Database

    return Database(DB_PATH)


def load_labpilot_config():
    """Load LabPilot config without exposing secrets.

    Review finding C3: thin wrapper around the unified loader.
    """
    return _load_unified_config()


def get_minimax_token_plan_config() -> TokenPlanConfig:
    """Return sanitized MiniMax token-plan configuration."""
    config = load_labpilot_config()
    ai_config = config.get("ai", {})
    env_api_key = os.getenv("LABPILOT_AI_API_KEY") or os.getenv("MINIMAX_API_KEY")
    file_api_key = ai_config.get("api_key")

    if env_api_key:
        api_key_source = "environment"
    elif file_api_key:
        api_key_source = "config"
    else:
        api_key_source = "missing"

    return TokenPlanConfig(
        provider=ai_config.get("provider", "minimax"),
        base_url=os.getenv("LABPILOT_AI_BASE_URL")
        or ai_config.get("base_url", "https://api.minimaxi.com/v1"),
        model=os.getenv("LABPILOT_AI_MODEL") or ai_config.get("model", "MiniMax-M2.7-highspeed"),
        timeout=int(os.getenv("LABPILOT_AI_TIMEOUT") or ai_config.get("timeout", 120)),
        language=os.getenv("LABPILOT_AI_LANGUAGE") or ai_config.get("language", "zh-CN"),
        max_diff_chars=int(
            os.getenv("LABPILOT_AI_MAX_DIFF_CHARS") or ai_config.get("max_diff_chars", 3000)
        ),
        has_api_key=bool(env_api_key or file_api_key),
        api_key_source=api_key_source,
    )


def init_db():
    """Initialize the database with the experiments table if it doesn't exist.

    Kept as a public helper for callers (e.g. CLI startup scripts) that
    want to bootstrap a Database. The FastAPI app runs this in the
    lifespan handler so DB initialization is no longer a side effect
    of importing ``api.main``.
    """
    from labpilot.database import Database

    Database(DB_PATH).init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the Database at app startup (review finding C2 + H6).

    Replaces the previous module-level ``init_db()`` call, which had
    three problems:
      * It ran at *import* time, so any code that imported ``api.main``
        (including tests) would touch ``./labpilot.db`` in cwd.
      * It ignored ``LABPILOT_DB_PATH`` set after import.
      * It had no shutdown hook.
    """
    from labpilot.database import Database

    db_path = os.getenv("LABPILOT_DB_PATH", DB_PATH)
    db = Database(db_path)
    db.init_db()
    app.state.db = db
    try:
        yield
    finally:
        # Per-request connections are closed via the context manager
        # in Database methods, so there is nothing to release here.
        # We keep the attribute for tests that introspect it.
        app.state.db = None


app = FastAPI(
    title="LabPilot API",
    description="API for managing ML experiments",
    lifespan=lifespan,
)

# Methods and headers are explicit allowlists (not "*"). Review finding
# H6: wildcard methods + headers with credentials would let any
# allowlisted origin perform state-changing requests and craft arbitrary
# authentication headers, weakening future auth additions.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=_cors_allows_credentials(),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/")
def read_root():
    return {"message": "Welcome to LabPilot API", "status": "running"}


@app.get(
    "/ai/token-plan",
    response_model=TokenPlanConfig,
    dependencies=[Depends(_require_read_key)],
)
def get_ai_token_plan():
    """
    Get sanitized MiniMax token-plan settings.
    """
    return get_minimax_token_plan_config()


@app.get(
    "/experiments",
    response_model=List[Experiment],
    dependencies=[Depends(_require_read_key)],
)
def get_experiments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    server: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db=Depends(_get_app_db),
):
    """
    Get a list of experiments with optional filtering and pagination
    """
    with db.connect() as conn:
        # Build the query with optional filters
        query = "SELECT * FROM experiments"
        conditions = []
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if server:
            conditions.append("server = ?")
            params.append(server)

        if search:
            conditions.append("(command LIKE ? OR log_snippet LIKE ? OR ckpt_path LIKE ?)")
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, skip])

        rows = conn.execute(query, params).fetchall()

    # Convert rows to Experiment objects
    return [Experiment(**dict(row)) for row in rows]


@app.post(
    "/experiments",
    response_model=Experiment,
    dependencies=[Depends(_require_write_key)],
)
def create_experiment(experiment: ExperimentCreate, db=Depends(_get_app_db)):
    """
    Create a new experiment record
    """
    current_time = datetime.now().isoformat()
    with db.connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO experiments
                (start_time, command, commit_hash, params, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                current_time,
                experiment.command,
                experiment.commit_hash,
                experiment.params,
                "running",
            ),
        )
        new_id = cursor.lastrowid

    return get_experiment(new_id, db=db)


@app.get(
    "/experiments/stats",
    dependencies=[Depends(_require_read_key)],
)
def get_experiment_stats(db=Depends(_get_app_db)):
    """
    Get statistics about experiments.

    NOTE: must be registered BEFORE the ``/{experiment_id}`` route
    below. FastAPI matches routes in declaration order, so a literal
    segment like ``stats`` would otherwise be parsed as an int path
    parameter and 422 before the right handler is reached.
    """
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) as count FROM experiments").fetchone()["count"]

        status_counts = {
            row["status"]: row["count"]
            for row in conn.execute(
                "SELECT status, COUNT(*) as count FROM experiments GROUP BY status"
            ).fetchall()
        }

        server_counts = {
            row["server"]: row["count"]
            for row in conn.execute(
                "SELECT server, COUNT(*) as count FROM experiments "
                "WHERE server IS NOT NULL GROUP BY server"
            ).fetchall()
        }

        recent = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM experiments
            WHERE start_time >= datetime('now', '-1 day')
            """
        ).fetchone()["count"]

    return {
        "total_experiments": total,
        "status_counts": status_counts,
        "server_counts": server_counts,
        "recent_experiments": recent,
        "last_updated": datetime.now().isoformat(),
    }


@app.get(
    "/experiments/{experiment_id}",
    response_model=Experiment,
    dependencies=[Depends(_require_read_key)],
)
def get_experiment(experiment_id: int, db=Depends(_get_app_db)):
    """
    Get a specific experiment by ID
    """
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return Experiment(**dict(row))


@app.put(
    "/experiments/{experiment_id}",
    response_model=Experiment,
    dependencies=[Depends(_require_write_key)],
)
def update_experiment(
    experiment_id: int,
    experiment_update: ExperimentUpdate,
    db=Depends(_get_app_db),
):
    """
    Update an existing experiment
    """
    # Build the update payload from Pydantic v2 (review finding H4).
    update_fields = []
    params = []

    for field, value in experiment_update.model_dump(exclude_unset=True).items():
        if value is not None:
            update_fields.append(f"{field} = ?")
            params.append(value)

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(experiment_id)
    query = f"UPDATE experiments SET {', '.join(update_fields)} WHERE id = ?"

    with db.connect() as conn:
        cursor = conn.execute(query, params)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Experiment not found")

    return get_experiment(experiment_id, db=db)


@app.delete(
    "/experiments/{experiment_id}",
    dependencies=[Depends(_require_write_key)],
)
def delete_experiment(experiment_id: int, db=Depends(_get_app_db)):
    """
    Hard-delete an experiment row.
    """
    with db.connect() as conn:
        cursor = conn.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Experiment not found")
    return {"message": "Experiment deleted successfully"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
