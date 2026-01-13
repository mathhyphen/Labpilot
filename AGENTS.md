# LabPilot Agent Guidelines

This document provides essential information for agentic coding agents working on the LabPilot codebase.

## Project Overview
LabPilot is a lightweight experiment management tool for deep learning researchers. It includes:
- A CLI tool (`labrun`) for tracking experiments.
- A FastAPI-based web dashboard.
- Notification integration (DingTalk, despite README mentioning ntfy).
- SQLite database for storage.

## Build and Installation
- **Language**: Python 3.7+
- **Installation**:
  ```bash
  pip install -e .
  ```
- **Dependencies**: Listed in `labpilot/requirements.txt` (FastAPI, Uvicorn, Pydantic, Requests, PyYAML).

## Testing
- **Status**: No explicit test suite found in the repository, despite `README.md` mentioning `./launch.sh test`.
- **Action**: If creating new features, consider adding a `tests/` directory with `pytest`.
- **Manual Verification**:
  - Run the CLI: `labrun --help`
  - Start the API: `uvicorn api.main:app --host 0.0.0.0 --port 8000`

## Code Style & Conventions

### Formatting
- **Indentation**: 4 spaces.
- **Line Length**: Adhere to standard PEP 8 (79-88 characters) where possible, but not strictly enforced.
- **Quotes**: Double quotes `"` are generally preferred for docstrings and strings.

### Language
- **Docstrings**: Chinese (Simplified). Use triple double quotes `"""`.
- **Comments**: Chinese (Simplified).
- **Naming**:
  - Variables/Functions: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_CASE`

### Type Hints
- Type hints are encouraged, especially for function arguments and return types (e.g., `def func(a: int) -> bool:`).
- See `labpilot/labpilot/notify.py` and `database.py` for examples.

### Imports
- Structure:
  1. Standard library imports (e.g., `os`, `sys`, `sqlite3`)
  2. Third-party imports (e.g., `requests`, `yaml`, `fastapi`)
  3. Local application imports (e.g., `from .database import get_db`)

### Error Handling
- Use `try-except` blocks for external operations (network requests, file I/O).
- Log errors clearly to console or via notification system.
- See `labpilot/labpilot/cli.py` for exception handling patterns.

## Configuration & Discrepancies
- **Notification System**: The code (`notify.py`, `cli.py`) explicitly implements **DingTalk** notifications. The `README.md` incorrectly claims support for **ntfy**. Agents should assume DingTalk is the supported notification channel unless implementing ntfy support.
- **Config Files**: Supported in order of precedence: `.labpilot.yaml` (cwd), `~/.labpilot.yaml` (home), `config.yaml` (package).

## Architecture
- **CLI (`labpilot/labpilot/cli.py`)**: Entry point, handles command execution, logging, and DB updates.
- **Database (`labpilot/labpilot/database.py`)**: SQLite wrapper using raw SQL queries (no ORM).
- **Notification (`labpilot/labpilot/notify.py`)**: Handles DingTalk API interaction.
- **API**: FastAPI application (in `labpilot/api/`).

## Git Integration
- The tool captures git commit hashes and can auto-snapshot changes.
- Uses `subprocess` to call git commands.
