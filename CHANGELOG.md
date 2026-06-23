# Changelog

All notable changes to LabPilot are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-06-09

### Security
- **API key authentication** — The FastAPI dashboard now requires
  `LABPILOT_API_KEY` for both reads and writes when set. Default-secure:
  no key ⇒ all writes (POST/PUT/DELETE) return 401, reads stay open.
  Accepts `X-API-Key: <key>` or `Authorization: Bearer <key>`. Constant-time
  comparison via `hmac.compare_digest`.
- **Webhook retry policy** — All JSON webhook notifiers (DingTalk,
  Feishu, WeCom, PushPlus, WxPusher) now retry transient network
  failures (Timeout, ConnectionError) and 5xx with exponential backoff
  (0.5s, 1s, 2s, ...). 4xx client errors are NOT retried.
- **Webhook URL validation** — ntfy, DingTalk, Feishu, and WeCom now
  validate the configured webhook URL scheme and host before sending,
  rejecting non-HTTPS / off-host endpoints that would leak tokens or
  enable SSRF.
- **Git pathspec separator** — `git add` and `git diff` invocations now
  insert an explicit `--` separator before user-supplied paths, so a
  path value that starts with `-` can no longer be parsed as a git flag.

### Added
- **QQ notifier** — push to QQ groups via the OneBot 11 HTTP API
  (self-hosted bot). One more `@register("qq")` class; no registry
  edit required.
- **Schema migration runner** — `Database.migrate()` brings forward
  legacy DBs that pre-date the migration system. New migrations are
  declared in the `_MIGRATIONS` list in `database.py`.
- **`pyproject.toml`** — Single source of truth for build metadata,
  ruff/mypy/pytest config, and dev extras. Replaces ad-hoc `setup.py`
  metadata and the per-tool config files (including `pytest.ini` — see
  Removed).
- **GitHub Actions CI** — `.github/workflows/ci.yml` runs ruff + mypy
  + the test matrix (Ubuntu + Windows × Python 3.9–3.12) on every push
  and PR.
- **Coverage gate** — `pytest-cov` with `--cov-fail-under=60` enforces
  a 60% coverage floor in CI.

### Changed
- **Configuration loader unified** — The four near-identical copies of
  the YAML-loading loop in `cli.py`, `git_utils.py`, `notify.py`, and
  `api/main.py` now all delegate to a single `labpilot.config.load_config()`.
- **Notification package split** — `notify.py` (660 lines) became a
  package with one module per channel + a `NOTIFIER_REGISTRY` +
  `@register()` decorator. Adding a new channel is two lines.
- **SQLite lifecycle** — Replaced the per-request `get_db_connection()`
  with a `Database` class whose `connect()` is a context manager that
  enables WAL + sets a 5 s busy timeout, and always closes (even on
  exception). The API now initialises the DB in a FastAPI lifespan
  handler — no more side effects on import.
- **Pydantic v2** — `update_experiment` migrated to
  `model_dump(exclude_unset=True)`. Pydantic 2.5+ is the minimum.
- **`extract_ckpt_path`** — Fixed a bug where the parsed filename was
  truncated to just `checkpoint.pth` (the regex captured the two
  groups separately and reassembled them, dropping the actual filename
  like `42` / `final` / `best_ema`).
- **OpenClaw notifier** — Fixed a Windows-only bug where a
  POSIX-style `cli_path` (no drive letter) was treated as relative
  even when the file existed. The resolver now probes `os.path.isfile`
  directly before falling back to `shutil.which`.
- **AST import walk** — `_collect_local_python_dependencies` now also
  picks up parent-package `__init__.py` files so scoped snapshots
  include the full package context.
- **FastAPI route ordering** — `/experiments/stats` is now registered
  before `/experiments/{experiment_id}`. FastAPI's declaration-order
  matching was routing `stats` as the int path parameter and 422-ing.

### Fixed
- **Windows `server_name` resolution** — `os.uname()` (POSIX-only) was
  replaced with `platform.node()` so `server_name` is populated on
  Windows instead of raising `AttributeError`. `server_name` and the
  AI-generated `commit_message` are now persisted to the DB instead of
  being computed and discarded.
- **`--timeout` terminates silent hung processes** — a child that
  stopped emitting output (but never exited) previously outlived the
  deadline because the reader thread kept `communicate()` alive. The
  runner now enforces the wall-clock deadline via a reader thread and
  kills the process group when it elapses.
- **Diagnostic logging** — broken logger expressions in `notify/base.py`
  and `notify/openclaw.py` (which raised on emission) are corrected;
  silent `except` blocks in `git_utils.py` now log the underlying error
  instead of swallowing it; `print()` calls in the AI commit-message
  generation path replaced with `logger`.

### Packaging
- **Dependency bumps** — `requests>=2.32.0` and `PyYAML>=6.0.1` (CVE
  coverage and Python 3.12 wheels). Removed unused `python-multipart`
  from runtime deps.
- **Dockerfile hardening** — image now runs as a non-root user and no
  longer installs dev extras (`pytest`, `ruff`, `mypy`) into the
  production image.

### Removed
- **`pytest.ini`** — deleted; `pyproject.toml` is now the single source
  of truth for pytest configuration.
- **Three global mutable singletons** — `_git_utils_instance`,
  `_db_instance`, and the API-side `get_db_connection()` global are
  gone. Constructors are explicit; tests no longer have to fight a
  module-level cache.

### Internal
- **`__version__`** now reads from installed package metadata
  (`importlib.metadata.version("labpilot")`) with a `"0+unknown"`
  fallback. Bumping `version` in `pyproject.toml` is reflected
  immediately on the next `pip install -e .` — no more drift between
  `__init__.py` and `setup.py`.
- **Module-level `print()` replaced with `logger.info/warning/error`**
  in `cli.py`, matching the structured-logging convention already used
  by the notifiers.

### Testing
- The suite has grown substantially (new files for API auth/endpoints,
  CLI helpers, config, DB lifecycle/migrations, git-utils AST, notify
  retry, version, and GPU wait). The passing count is no longer
  hardcoded here — see CI for the current matrix result.

## [2.1.0] - 2026-06-03

### Security (CRITICAL)
- **Feishu HMAC signature was broken** — `key` and `message` arguments to
  `hmac.new()` were swapped, AND the timestamp was in seconds instead of
  milliseconds. Every Feishu webhook configured with `secret` was silently
  rejected. Now matches the official algorithm (key=secret, msg=ts+`\n`+secret)
  with millisecond timestamps.
- **PushPlus endpoint upgraded to HTTPS** — the request body carries the
  user's PushPlus token bound to a personal WeChat account, so the previous
  HTTP endpoint leaked the credential on any shared or hostile network.
- **OpenClaw `cli_path` validation** — the resolved binary's basename must
  start with `openclaw` AND the file must actually exist. Prevents a config
  that points `cli_path` at `/bin/rm` or any other arbitrary executable
  from turning every `labrun` into a silent exec vector.
- **CORS hardening** — origins now read from `LABPILOT_CORS_ORIGINS` env
  var (default `http://localhost:8000`); credentials are auto-disabled when
  origins is `*`; methods narrowed to `GET/POST/PUT/DELETE`; headers narrowed
  to `Content-Type/Authorization`.
- **WxPusher `base_url` allowlist** — reject any host outside
  `wxpusher.zjiecode.com` or any non-HTTPS scheme. Stops SSRF abuse that
  would also leak the `app_token`.

### Reliability
- **Subprocess timeouts** — every `subprocess.run` call in `git_utils.py`
  and `cli.py` (12 sites) now carries `timeout=DEFAULT_SUBPROCESS_TIMEOUT`
  (30s). A hung `nvidia-smi` or stalled git process no longer blocks
  `labrun` indefinitely.
- **Bare `except:` fixed** — `cli.py`'s `KeyboardInterrupt` handler used
  a bare `except:` that also swallowed `KeyboardInterrupt` and `SystemExit`,
  making the wrapper unkillable. Replaced with a narrow
  `(ProcessLookupError, OSError)` catch via a new `safe_kill_process`
  helper.
- **Structured logging** — `print()` replaced with `logger.info/error`
  throughout all notifiers. New `_post_json_notifier` helper centralises
  `raise_for_status()`, narrow exception handling, and whitelisted
  error-field logging (so the full response body, which can echo the
  token, is never dumped).
- **OpenClaw `user_id` validation** — reject values starting with `-`
  or containing whitespace, to prevent argument smuggling into the CLI
  call (e.g. `user_id="--help"`).

### Added
- **PushPlus notifier** — push to personal WeChat via
  pushplus.plus (WeChat official account template messages). Free tier
  200 msgs/day. HTTP POST with markdown/HTML/txt templates.
- **WxPusher notifier** — push to personal WeChat via
  wxpusher.zjiecode.com (WeChat test account). Rich HTML, individual
  or topic-based delivery.
- **OpenClaw CLI notifier** — push to personal WeChat via Tencent's
  official ClawBot plugin (iLink protocol, released 2026/03/22). Wraps
  the `openclaw send` CLI for users with an existing OpenClaw
  deployment. Plugin is in gradual rollout — iOS WeChat ≥ 8.0.70,
  Android ≥ 8.0.69.

### Testing
- Added `pytest.ini` and `conftest.py` so the previously-broken
  `test_api_config.py` is now collectable.
- Added 4 new test files (`test_cli.py`, `test_api_cors.py`,
  `test_subprocess_timeouts.py`, `test_openclaw_notifier.py`) with
  41 new test cases. Total suite: **46/46 passing** in 1.3s.

### Documentation
- `README.md` documents the three new notifier channels with setup
  instructions.
- `AGENTS.md` no longer claims DingTalk is the only supported channel;
  lists all seven channels and the unified `get_notifier()` dispatch.
- `config.yaml` includes a documented `pushplus`, `wxpusher`, and
  `openclaw` block with comments explaining each option.

## [2.0.6] - 2026-05-27

### Added
- Chat robot notifications and scoped snapshots.

## [2.0.5] - 2026-04-01

### Added
- AI auto-commit with MiniMax/OpenAI-compatible LLM.

## [2.0.0] - 2026-01-22

### Added
- Initial public release with GPU scheduling, config enhancements,
  and multi-channel notifications (DingTalk, Feishu, WeCom, ntfy).
