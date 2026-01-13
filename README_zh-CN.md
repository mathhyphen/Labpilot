[English](README.md) | **简体中文**

# LabPilot - AI 驱动的轻量级实验管理助手

LabPilot 是专为深度学习研究者设计的极简实验管理工具。告别繁琐的手动记录，LabPilot 自动帮你管理代码版本、监控实验状态，并通过 AI 自动生成提交信息。

## ✨ 核心特性

- **🤖 AI 辅助 Git**：自动检测代码变动，调用大模型（LLM）生成清晰的 Git Commit Message 并自动提交。
- **📊 自动实验跟踪**：一键运行，自动记录命令、参数、时间、Git 版本和运行结果。
- **📱 实时通知**：支持 **DingTalk (钉钉)** 和 **ntfy**，随时随地掌握实验进度。
- **🌐 多服务器支持**：支持自定义服务器名称，集中管理多台机器的实验记录。
- **⚡️ 零侵入**：无需修改代码，只需在命令前加上 `labrun`。

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/mathhyphen/Labpilot.git
cd Labpilot
pip install -e .
```

### 2. 配置

LabPilot 支持 `.labpilot.yaml` (当前目录) 或 `~/.labpilot.yaml` (用户目录)。

**推荐配置：**

```yaml
# 服务器名称（多服务器场景非常有用）
server_name: "GPU-Server-01"

# AI 自动 Commit 配置 (支持 OpenAI 格式 API)
ai:
  api_key: "your-api-key"
  base_url: "https://open.bigmodel.cn/api/paas/v4/" # 默认智谱 AI，可换成其他 OpenAI 兼容接口
  model: "glm-4"

# 通知配置
notification:
  active: [dingtalk] # 或 [dingtalk, ntfy]
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
```

## 🧠 AI 驱动的 Git 流程

LabPilot 的核心功能之一是**自动化版本控制**。当您运行实验时：

1. 检测当前代码是否有未提交的更改。
2. 如果有更改，自动收集 `git diff`。
3. **调用配置的 LLM API** 分析代码变动。
4. 生成语义化的 Commit Message（例如："feat: add learning rate scheduler"）。
5. 自动执行 `git commit` 保存实验现场快照。

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

## 📊 Web 仪表板

启动内置的 Web 界面查看所有实验历史：

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
