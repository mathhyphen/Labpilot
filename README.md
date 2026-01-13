**English** | [简体中文](README_zh-CN.md)

# LabPilot - AI-Powered Lightweight Experiment Manager

LabPilot is a minimalist experiment management tool designed for deep learning researchers. It automates experiment tracking, version control, and notifications with zero code changes.

## ✨ Key Features

- **🤖 AI-Powered Git**: Automatically detects code changes, uses LLMs to generate semantic Git commit messages, and creates snapshots before experiments.
- **📊 Auto Tracking**: Records commands, parameters, timestamps, Git commits, and execution results automatically.
- **📱 Real-time Notifications**: Supports **DingTalk** and **ntfy** for instant updates on your phone.
- **🌐 Multi-Server Support**: Custom server names for centralized management of experiments across multiple machines.
- **⚡️ Zero Intrusion**: Just prepend `labrun` to your command. No code modification required.

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/mathhyphen/Labpilot.git
cd Labpilot
pip install -e .
```

### 2. Configuration

Create a config file at `.labpilot.yaml` (current dir) or `~/.labpilot.yaml` (home dir).

**Recommended Configuration:**

```yaml
# Server Identifier
server_name: "GPU-Server-01"

# AI Auto-Commit Configuration (OpenAI Compatible)
ai:
  api_key: "your-api-key"
  base_url: "https://open.bigmodel.cn/api/paas/v4/" # Default: Zhipu AI
  model: "glm-4"

# Notification Configuration
notification:
  active: [dingtalk] # or [dingtalk, ntfy]
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
```

## 🧠 AI-Driven Git Workflow

One of LabPilot's core features is **Automated Version Control**. When you launch an experiment:

1. Checks for uncommitted code changes.
2. Captures `git diff` if changes exist.
3. **Calls the configured LLM API** to analyze code changes.
4. Generates a meaningful commit message (e.g., "feat: add learning rate scheduler").
5. Automatically executes `git commit` to snapshot the experiment state.

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

## 📊 Web Dashboard

Launch the built-in web dashboard to view experiment history:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
