[English](README.md) | **简体中文**

# LabPilot - AI 驱动的轻量级实验管理助手

[![最新版](https://img.shields.io/github/v/release/mathhyphen/Labpilot?label=release)](https://github.com/mathhyphen/Labpilot/releases/latest)

LabPilot 是专为深度学习研究者设计的极简实验管理工具。告别繁琐的手动记录，LabPilot 自动帮你管理代码版本、监控实验状态，并通过 AI 自动生成提交信息。

## ✨ 核心特性

- **🤖 AI 辅助 Git**：使用 MiniMax 或其他 OpenAI 兼容大模型总结脚本变动，并在实验前创建快照。
- **📊 自动实验跟踪**：一键运行，自动记录命令、参数、时间、Git 版本和运行结果。
- **🔍 显卡检测**：自动检测可用显卡，记录 GPU 信息（NVIDIA、AMD），为实验提供更好的硬件环境记录。
- **📱 实时通知**：支持 **DingTalk (钉钉)**、**ntfy**、**飞书** 和 **企业微信/微信机器人**，随时随地掌握实验进度。
- **🧹 精准 Git 快照**：运行脚本时只提交入口脚本及相关本地 Python 依赖改动，不污染无关工作。
- **🌐 多服务器支持**：支持自定义服务器名称，集中管理多台机器的实验记录。
- **⚡️ 零侵入**：无需修改代码，只需在命令前加上 `labrun`。

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/mathhyphen/Labpilot.git
cd Labpilot
pip install -e .
```

也可以从 [GitHub Releases](https://github.com/mathhyphen/Labpilot/releases/latest) 下载最新版源码包。

### 2. 配置

LabPilot 支持 `.labpilot.yaml` (当前目录) 或 `~/.labpilot.yaml` (用户目录)。

**推荐配置：**

```yaml
# 服务器名称（多服务器场景非常有用）
server_name: "GPU-Server-01"

# AI 自动 Commit 配置 (支持 OpenAI 格式 API)
ai:
  provider: "minimax"
  api_key: "" # 推荐使用 LABPILOT_AI_API_KEY 或 MINIMAX_API_KEY 环境变量
  base_url: "https://api.minimaxi.com/v1"
  model: "MiniMax-M2.7-highspeed"
  max_diff_chars: 3000

# 通知配置
notification:
  active: [dingtalk] # 或 [dingtalk, ntfy, feishu, wecom]
  dingtalk:
    webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=..."
```

### 3. 使用

就像使用 `nohup` 或 `sudo` 一样，在你的训练命令前加上 `labrun`：

```bash
# 运行训练脚本
labrun python train.py --epochs 100 --lr 1e-4

# 指定超时时间（例如 5 小时后自动停止）
labrun --timeout 18000 python train.py

# 等待显存足够的GPU（例如等待空闲显存 >12GB 的GPU）
labrun --wait-gpu 12g python train.py --epochs 100 --lr 1e-4

# 等待指定显存的GPU（以MB为单位）
labrun --wait-gpu 10240m python train.py --batch_size 64

# 等待任何可用的GPU
labrun --wait-gpu any python train.py --epochs 50
```

## 🧠 AI 驱动的 Git 流程

LabPilot 的核心功能之一是**自动化版本控制**。当您运行实验时：

1. 从命令中识别入口脚本。
2. 查找入口脚本及其本地 Python import 依赖中的未提交改动。
3. 只收集这些关联文件的 `git diff`。
4. **调用配置的 LLM API** 总结脚本变动。
5. 自动执行 `git commit --only`，避免把无关的已暂存或未暂存文件带进实验快照。

这确保了您的每一次实验记录都严格对应唯一的代码版本，且拥有可读的历史记录。

## 🔧 高级配置

### 多服务器共享数据

将 `database.path` 指向共享存储（如 NFS）：

```yaml
database:
  path: "/mnt/nfs/labpilot/shared.db"
```

### ntfy 通知配置

```yaml
notification:
  active: [ntfy]
  ntfy:
    topic: "my-secret-topic" # 订阅主题
    server: "https://ntfy.sh"
```

### 飞书和企业微信通知

```yaml
notification:
  active: [feishu, wecom]
  feishu:
    webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/..."
    secret: "" # 可选
  wecom:
    webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
```

### MiniMax Token Plan API

建议在 shell 中设置 `LABPILOT_AI_API_KEY` 或 `MINIMAX_API_KEY`，不要把真实 token 写进配置文件。Dashboard API 提供一个脱敏配置检查接口：

```bash
GET /ai/token-plan
```

### 显卡检测和自动选择

LabPilot 自动检测可用的NVIDIA显卡并提供智能GPU排队功能：

**显存格式示例：**
- `12g` = 12 GB
- `10240m` = 10240 MB
- `any` = 任何可用的GPU

**工作原理：**
1. 使用 `nvidia-smi` 查询GPU显存状态
2. 找到空闲显存足够的GPU
3. 自动设置 `CUDA_VISIBLE_DEVICES` 环境变量
4. 等待直到合适的GPU可用

**命令示例：**
```bash
# 等待空闲显存 >8GB 的GPU
labrun --wait-gpu 8g python train.py

# 等待空闲显存 >16384MB 的GPU
labrun --wait-gpu 16384m python train.py

# 不等待GPU直接运行（使用默认GPU）
labrun python train.py

# 结合超时设置使用
labrun --wait-gpu 12g --timeout 3600 python train.py
```

## 📊 Web 仪表板

启动内置的 Web 界面查看所有实验历史：

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
