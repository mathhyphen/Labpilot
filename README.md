**English** | [简体中文](README_zh-CN.md)

# LabPilot - AI-Powered Lightweight Experiment Manager

LabPilot is a minimalist experiment management tool designed for deep learning researchers. It automates experiment tracking, version control, and notifications with zero code changes.

## ✨ Key Features

- **🤖 AI-Powered Git**: Automatically detects code changes, uses LLMs to generate semantic Git commit messages, and creates snapshots before experiments.
- **📊 Auto Tracking**: Records commands, parameters, timestamps, Git commits, and execution results automatically.
- **🔍 GPU Detection**: Automatically detects available GPUs and records GPU information (NVIDIA, AMD) for better experiment context.
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

# Wait for GPU with sufficient memory (e.g., wait for GPU with >12GB free memory)
labrun --wait-gpu 12g python train.py --epochs 100 --lr 1e-4

# Wait for GPU with specific memory in MB
labrun --wait-gpu 10240m python train.py --batch_size 64

# Wait for any available GPU
labrun --wait-gpu any python train.py --epochs 50
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
