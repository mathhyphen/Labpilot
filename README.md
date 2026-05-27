**English** | [简体中文](README_zh-CN.md)

# LabPilot - AI-Powered Lightweight Experiment Manager

[![Latest Release](https://img.shields.io/github/v/release/mathhyphen/Labpilot?label=release)](https://github.com/mathhyphen/Labpilot/releases/latest)

LabPilot is a minimalist experiment management tool designed for deep learning researchers. It automates experiment tracking, version control, and notifications with zero code changes.

## ✨ Key Features

- **🤖 AI-Powered Git**: Uses MiniMax or any OpenAI-compatible LLM to summarize script changes and create scoped snapshots before experiments.
- **📊 Auto Tracking**: Records commands, parameters, timestamps, Git commits, and execution results automatically.
- **🔍 GPU Detection**: Automatically detects available GPUs and records GPU information (NVIDIA, AMD) for better experiment context.
- **📱 Real-time Notifications**: Supports **DingTalk**, **ntfy**, **Feishu/Lark**, and **WeCom/WeChat Work** robot notifications.
- **🧹 Scoped Git Snapshots**: When running a script, LabPilot only commits the entry script and related local Python dependencies, leaving unrelated work untouched.
- **🌐 Multi-Server Support**: Custom server names for centralized management of experiments across multiple machines.
- **⚡️ Zero Intrusion**: Just prepend `labrun` to your command. No code modification required.

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/mathhyphen/Labpilot.git
cd Labpilot
pip install -e .
```

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
  active: [dingtalk] # or [dingtalk, ntfy, feishu, wecom]
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

## 📊 Web Dashboard

Launch the built-in web dashboard to view experiment history:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
