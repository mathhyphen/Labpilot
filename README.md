**English** | [简体中文](README_zh-CN.md)

# LabPilot - AI-Powered Lightweight Experiment Manager

[![Latest Release](https://img.shields.io/github/v/release/mathhyphen/Labpilot?label=release)](https://github.com/mathhyphen/Labpilot/releases/latest)

LabPilot is a minimalist experiment management tool designed for deep learning researchers. It automates experiment tracking, version control, and notifications with zero code changes.

## ✨ Key Features

- **🤖 AI-Powered Git**: Uses MiniMax or any OpenAI-compatible LLM to summarize script changes and create scoped snapshots before experiments.
- **📊 Auto Tracking**: Records commands, parameters, timestamps, Git commits, and execution results automatically.
- **🔍 GPU Detection**: Automatically detects available GPUs and records GPU information (NVIDIA; AMD not supported) for better experiment context.
- **📱 Real-time Notifications**: Supports **DingTalk**, **ntfy**, **Feishu/Lark**, **WeCom/WeChat Work**, **PushPlus**, **WxPusher** (personal WeChat), **OpenClaw** (personal WeChat via Tencent's official ClawBot plugin), and **QQ via OneBot** (self-hosted bot).
- **🧹 Scoped Git Snapshots**: When running a script, LabPilot only commits the entry script and related local Python dependencies, leaving unrelated work untouched.
- **🌐 Multi-Server Support**: Custom server names for centralized management of experiments across multiple machines.
- **⚡️ Zero Intrusion**: Just prepend `labrun` to your command. No code modification required.

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/mathhyphen/Labpilot.git
cd Labpilot
pip install -e ".[dev]"
```

The dev extras add `pytest`, `pytest-cov`, `ruff`, and `mypy` so you can run the test suite and the linter locally. For a runtime-only install, drop the `[dev]`.

Or download the latest source distribution from [GitHub Releases](https://github.com/mathhyphen/Labpilot/releases/latest).

### 2. Configuration

Create a config file at `.labpilot.yaml` (current dir) or `~/.labpilot.yaml` (home dir).

**Recommended Configuration:**

```yaml
# Server Identifier
server_name: "GPU-Server-01"

# AI Auto-Commit Configuration (OpenAI Compatible)
ai:
  provider: "minimax"
  api_key: "" # Prefer LABPILOT_AI_API_KEY or MINIMAX_API_KEY env vars
  base_url: "https://api.minimaxi.com/v1"
  model: "MiniMax-M2.7-highspeed"
  max_diff_chars: 3000

# Notification Configuration
notification:
  active: [dingtalk] # or [feishu, pushplus, wxpusher, openclaw, qq, onebot, ...]
  dingtalk:
    webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=..."
```

### 3. Usage

Simply add `labrun` before your training command:

```bash
# Run training script
labrun python train.py --epochs 100 --lr 1e-4

# Set timeout (e.g., stop after 5 hours)
labrun --timeout 18000 python train.py

# Wait for GPU with sufficient memory (e.g., wait for GPU with >12GB free memory)
labrun --wait-gpu 12g python train.py --epochs 100 --lr 1e-4

# Wait for GPU with specific memory in MB
labrun --wait-gpu 10240m python train.py --batch_size 64

# Wait for any available GPU
labrun --wait-gpu any python train.py --epochs 50
```

## 🧠 AI-Driven Git Workflow

One of LabPilot's core features is **Automated Version Control**. When you launch an experiment:

1. Detects the entry script from your command.
2. Finds uncommitted changes in that script and its local Python imports.
3. Captures a scoped `git diff` for only those related files.
4. **Calls the configured LLM API** to summarize the changes.
5. Automatically executes `git commit --only` so unrelated staged or unstaged files are not included.

This ensures every experiment run is strictly tied to a specific code version with readable history.

## 🔧 Advanced Configuration

### Multi-Server Data Sharing

Point `database.path` to a shared storage (e.g., NFS):

```yaml
database:
  path: "/mnt/nfs/labpilot/shared.db"
```

### ntfy Notification

```yaml
notification:
  active: [ntfy]
  ntfy:
    topic: "my-secret-topic"
    server: "https://ntfy.sh"
```

### Feishu and WeCom Notifications

```yaml
notification:
  active: [feishu, wecom]
  feishu:
    webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/..."
    secret: "" # optional
  wecom:
    webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
```

### Personal WeChat via PushPlus / WxPusher

Both services push to your **personal WeChat** through a WeChat official account — no group bot required.

```yaml
notification:
  active: [pushplus]  # or wxpusher
  pushplus:
    token: "your-pushplus-token"  # get from pushplus.plus after scanning the QR code
    template: "markdown"
  wxpusher:
    app_token: "your-app-token"  # from wxpusher.zjiecode.com
    uids: ["uid_xxxxx"]          # the uid you got after scanning
```

- **PushPlus** — Free 200 messages/day, markdown templates. Setup: scan the QR at pushplus.plus, copy your token.
- **WxPusher** — Rich HTML, individual or topic-based push. Setup: create an app at wxpusher.zjiecode.com, share the QR, collect uids.

### Personal WeChat via OpenClaw (ClawBot plugin)

For users with a deployed **OpenClaw** instance bound to the **ClawBot** plugin (Tencent's official iLink protocol for personal WeChat, released 2026/03/22):

```yaml
notification:
  active: [openclaw]
  openclaw:
    cli_path: "openclaw"          # or absolute path
    user_id: "your-wechat-user-id"
    timeout: 10
```

Prerequisites: Node.js 22+, `npm i -g openclaw@latest`, WeChat iOS ≥ 8.0.70 / Android ≥ 8.0.69, enable ClawBot in *Me → Settings → Plugins*. The plugin is in gradual rollout; not all accounts have access yet.

### QQ via OneBot (self-hosted bot)

Push to a QQ account or group through a self-hosted OneBot v11 implementation. Both `qq` and `onebot` are valid `active:` names.

```yaml
notification:
  active: [qq]  # or [onebot]
  qq:
    base_url: "http://127.0.0.1:5700"   # your OneBot v11 HTTP endpoint
    access_token: "your-access-token"    # bearer token configured in the bot
    user_id: "123456789"                 # private-message target (omit for group)
    group_id: "987654321"                # group-message target (omit for private)
    auto_escape: true                    # render the message as plain text
```

Prerequisite: a self-hosted Lagrange.OneBot or go-cqhttp instance exposing the OneBot v11 HTTP API.

### MiniMax Token Plan API

Set `LABPILOT_AI_API_KEY` or `MINIMAX_API_KEY` in your shell instead of committing it to config files. The dashboard API exposes a sanitized config check at:

```bash
GET /ai/token-plan
```

### GPU Detection and Auto-Selection

LabPilot automatically detects available NVIDIA GPUs and provides smart GPU queuing:

**Memory Format Examples:**
- `12g` = 12 GB
- `10240m` = 10240 MB  
- `any` = any available GPU

**How it works:**
1. Uses `nvidia-smi` to query GPU memory status
2. Finds GPUs with sufficient free memory
3. Automatically sets `CUDA_VISIBLE_DEVICES` environment variable
4. Waits until a suitable GPU becomes available

**Command Examples:**
```bash
# Wait for GPU with >8GB free memory
labrun --wait-gpu 8g python train.py

# Wait for GPU with >16384MB free memory  
labrun --wait-gpu 16384m python train.py

# Run without GPU waiting (use default GPU)
labrun python train.py

# Combine with timeout
labrun --wait-gpu 12g --timeout 3600 python train.py
```

## 📊 JSON API / Dashboard Backend

Launch the built-in HTTP API to query experiment history. It serves JSON only — there are no mounted HTML or static-file routes, so point your own dashboard or script at the endpoints below:

```bash
# Without auth (local-only usage)
uvicorn api.main:app --host 0.0.0.0 --port 8000

# With API key auth (recommended when exposing to a network)
export LABPILOT_API_KEY="$(openssl rand -hex 32)"
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The API reads from the same SQLite database the CLI writes to. See the endpoints below for the schema; once `LABPILOT_API_KEY` is set, all write endpoints require `X-API-Key: <key>` (or `Authorization: Bearer <key>`).

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET`  | `/`                       | Liveness probe |
| `GET`  | `/ai/token-plan`          | Sanitised AI provider config (no secrets) |
| `GET`  | `/experiments`            | List experiments (supports `?status=`, `?server=`, `?search=`, `?skip=`, `?limit=`) |
| `POST` | `/experiments`            | Insert a new `running` experiment |
| `GET`  | `/experiments/{id}`       | Fetch a single experiment |
| `PUT`  | `/experiments/{id}`       | Update an experiment (end_time, status, log_snippet, …) |
| `DELETE` | `/experiments/{id}`     | Hard-delete an experiment |
| `GET`  | `/experiments/stats`      | Aggregate counts (total, by status, by server, last 24 h) |

## 🛡️ Security

- **API key auth** (v2.2.0+): `LABPILOT_API_KEY` env var gates all reads and writes. Comparison via `hmac.compare_digest`. Default-secure — no key ⇒ all writes return 401, reads stay open for local use.
- **Webhook retry** (v2.2.0+): JSON webhook notifiers retry transient network errors and 5xx with exponential backoff. 4xx is never retried.
- **Webhook URL allowlisting** (v2.2.0+): DingTalk / Feishu / WeCom / ntfy webhook URLs are validated for scheme (`https`, or `http` only for self-hosted ntfy/OneBot) and a fixed host allowlist, preventing SSRF and credential capture.
- **Subprocess timeouts** (v2.1.0+): every `subprocess.run` carries `timeout=30 s` so a hung `git` or `nvidia-smi` cannot block `labrun` indefinitely.
- **SQLite resilience** (v2.2.0+): every connection opens in WAL mode with a 5 s busy timeout. Concurrent labrun writes + dashboard reads are now safe.
- **OpenClaw `cli_path`** is restricted to binaries whose basename starts with `openclaw` and that exist on disk. `user_id` is rejected if it starts with `-` or contains whitespace (argument smuggling).
- **WxPusher `base_url`** is allowlisted to `wxpusher.zjiecode.com` (no SSRF abuse).
- **PushPlus endpoint** is hardcoded to HTTPS (the request body carries the user's PushPlus token).

## 🧪 Development

```bash
# Run the test suite
python -m pytest

# With coverage (60 % gate)
python -m pytest  # already wired via pyproject.toml

# Lint
ruff check .
ruff format --check .

# Type-check
mypy labpilot/labpilot labpilot/api
```

CI runs on every push via `.github/workflows/ci.yml` (lint + typecheck + tests on Ubuntu + Windows × Python 3.9 – 3.12).
