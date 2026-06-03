# Changelog

All notable changes to LabPilot are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
