# LabPilot Agent Guidelines

This document provides essential information for agentic coding agents working on the LabPilot codebase.

## Project Overview
LabPilot is a lightweight experiment management tool for deep learning researchers. It includes:
- A CLI tool (`labrun`) for tracking experiments.
- A FastAPI-based web dashboard with API-key auth.
- Notification integration: **DingTalk**, **Feishu/Lark**, **WeCom/WeChat Work**, **ntfy**, **PushPlus** (personal WeChat), **WxPusher** (personal WeChat), **OpenClaw CLI** (personal WeChat via ClawBot plugin).
- SQLite database for storage with WAL + busy_timeout.

## Build and Installation
- **Language**: Python 3.9+
- **Installation**:
  ```bash
  pip install -e ".[dev]"
  ```
- **Dependencies**: Declared in `pyproject.toml`. Runtime: FastAPI, Uvicorn, Pydantic 2, Requests, PyYAML. Dev extras add pytest, pytest-cov, ruff, mypy.

## Testing
- All tests live under `tests/` and run with `python -m pytest tests/` from the repo root.
- `pyproject.toml` configures `pythonpath = ["labpilot"]` so the inner package is importable.
- Coverage is enforced at 60% (`--cov-fail-under=60`); aim higher when adding modules.
- Run the labpilot CLI: `labrun --help`
- Run the API: `uvicorn api.main:app --host 0.0.0.0 --port 8000` (from the `labpilot/` subdir)

## Code Style & Conventions

### Formatting
- **Indentation**: 4 spaces.
- **Line Length**: 100 (ruff default in `pyproject.toml`).
- **Quotes**: Double quotes `"` are generally preferred for docstrings and strings.

### Language
- **Docstrings**: Chinese (Simplified). Use triple double quotes `"""`.
- **Comments**: Chinese (Simplified).
- **Naming**:
  - Variables/Functions: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_CASE`

### Type Hints
- Type hints are encouraged, especially for function arguments and return types.
- The codebase uses `Optional[T]`, `List[T]`, `Dict[K, V]` from `typing`. (The `T | None` PEP 604 syntax requires Python 3.10+.)
- See `labpilot/labpilot/notify/base.py` and `database.py` for examples.

### Imports
- Structure:
  1. Standard library imports (e.g., `os`, `sys`, `sqlite3`)
  2. Third-party imports (e.g., `requests`, `yaml`, `fastapi`)
  3. Local application imports (e.g., `from .database import Database`)

### Error Handling
- Use `try-except` blocks for external operations (network requests, file I/O).
- Log errors via the module-level `logger = logging.getLogger(__name__)`, **never `print()`**.
- The webhook notifiers retry transient failures with exponential backoff; client errors (4xx) are not retried.

## Configuration & Discrepancies
- **Notification System**: All seven channels live in `labpilot/notify/<channel>.py`. Each notifier is registered via the `@register("name", *aliases)` decorator in `labpilot/notify/registry.py`. The dispatcher (`get_notifier()`) consults the registry — adding a new channel is one line in two places (the new file's import in `__init__.py` and the `@register` call).
- **Config Files**: Precedence `.labpilot.yaml` (cwd) → `~/.labpilot.yaml` (home) → `<pkg>/config.yaml` (default). The single source of truth is `labpilot.config.load_config()`; the four legacy wrappers in `cli.py` / `git_utils.py` / `notify.py` / `api/main.py` all delegate to it.

## Architecture
- **CLI (`labpilot/labpilot/cli.py`)**: Entry point, handles command execution, logging, and DB updates. The `main()` function is hard to test in isolation (it spawns subprocesses); the pure helpers (`extract_params`, `parse_memory_str`, `extract_ckpt_path`, `safe_kill_process`) are tested directly.
- **Database (`labpilot/labpilot/database.py`)**: `Database` class with `connect()` context manager (WAL + busy_timeout). Schema migrations are declared in `_MIGRATIONS` and applied by `Database.migrate()`.
- **Notifications (`labpilot/labpilot/notify/`)**: Package with one module per channel. Shared base class with retry/backoff in `BaseNotifier._post_json_notifier`.
- **API (`labpilot/api/main.py`)**: FastAPI app. Endpoints require API-key auth (see "Security" below).

## Security
- **API auth**: Set `LABPILOT_API_KEY` env var to enable. Reads (GET) and writes (POST/PUT/DELETE) both require the key, accepted as `X-API-Key: <key>` or `Authorization: Bearer <key>`. Constant-time comparison via `hmac.compare_digest`.
- **Default-secure**: With no key set, all mutating endpoints return 401. Read endpoints stay open so a local dashboard works without configuration.
- **Webhook URLs**: The WxPusher `base_url` is allowlisted; PushPlus endpoint is hardcoded HTTPS. Other webhook URLs are passed through, so do not put credentials in URL paths.
- **OpenClaw `cli_path`**: Allowlisted to binaries whose basename starts with `openclaw` and that exist on disk. `user_id` is rejected if it starts with `-` or contains whitespace (argument smuggling).

## Git Integration
- The tool captures git commit hashes and can auto-snapshot changes.
- Uses `subprocess` (with `timeout=30` on every call) to run git commands.
- AST-based import walking (`_collect_local_python_dependencies`) determines which files belong to the experiment. Walks the import graph recursively, follows into parent package `__init__.py`, and refuses to leave the repo root.
