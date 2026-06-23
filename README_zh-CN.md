[English](README.md) | **简体中文**

# LabPilot - AI 驱动的轻量级实验管理助手

[![最新版](https://img.shields.io/github/v/release/mathhyphen/Labpilot?label=release)](https://github.com/mathhyphen/Labpilot/releases/latest)

LabPilot 是专为深度学习研究者设计的极简实验管理工具。它自动完成实验跟踪、版本控制和通知，无需改动任何代码。

## ✨ 核心特性

- **🤖 AI 辅助 Git**：使用 MiniMax 或任何 OpenAI 兼容大模型总结脚本变动，并在实验前创建精准快照。
- **📊 自动跟踪**：自动记录命令、参数、时间戳、Git 提交和执行结果。
- **🔍 显卡检测**：自动检测可用 GPU 并记录 GPU 信息（仅支持 NVIDIA），为实验提供更好的硬件环境记录。
- **📱 实时通知**：支持 **钉钉 (DingTalk)**、**ntfy**、**飞书/Lark**、**企业微信/WeCom**、**PushPlus**、**WxPusher**（个人微信）、**OpenClaw**（通过腾讯官方 ClawBot 插件推送至个人微信）以及 **QQ（OneBot，自建机器人）**。
- **🧹 精准 Git 快照**：运行脚本时只提交入口脚本及相关本地 Python 依赖改动，不污染无关工作。
- **🌐 多服务器支持**：支持自定义服务器名称，集中管理多台机器的实验记录。
- **⚡️ 零侵入**：只需在命令前加上 `labrun`，无需修改代码。

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/mathhyphen/Labpilot.git
cd Labpilot
pip install -e ".[dev]"
```

`[dev]` 额外依赖会安装 `pytest`、`pytest-cov`、`ruff` 和 `mypy`，方便你在本地运行测试套件和 linter。如果只需运行时依赖，去掉 `[dev]` 即可。

也可以从 [GitHub Releases](https://github.com/mathhyphen/Labpilot/releases/latest) 下载最新版源码包。

### 2. 配置

在 `.labpilot.yaml`（当前目录）或 `~/.labpilot.yaml`（用户目录）创建配置文件。

**推荐配置：**

```yaml
# 服务器标识
server_name: "GPU-Server-01"

# AI 自动提交配置（OpenAI 兼容）
ai:
  provider: "minimax"
  api_key: "" # 推荐使用 LABPILOT_AI_API_KEY 或 MINIMAX_API_KEY 环境变量
  base_url: "https://api.minimaxi.com/v1"
  model: "MiniMax-M2.7-highspeed"
  max_diff_chars: 3000

# 通知配置
notification:
  active: [dingtalk] # 或 [feishu, pushplus, wxpusher, openclaw, ...]
  dingtalk:
    webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=..."
```

### 3. 使用

只需在训练命令前加上 `labrun`：

```bash
# 运行训练脚本
labrun python train.py --epochs 100 --lr 1e-4

# 设置超时时间（例如 5 小时后停止）
labrun --timeout 18000 python train.py

# 等待显存足够的 GPU（例如等待空闲显存 >12GB 的 GPU）
labrun --wait-gpu 12g python train.py --epochs 100 --lr 1e-4

# 等待指定显存的 GPU（以 MB 为单位）
labrun --wait-gpu 10240m python train.py --batch_size 64

# 等待任何可用的 GPU
labrun --wait-gpu any python train.py --epochs 50
```

## 🧠 AI 驱动的 Git 流程

LabPilot 的核心功能之一是**自动化版本控制**。当你启动一个实验时：

1. 从命令中识别入口脚本。
2. 查找入口脚本及其本地 Python import 依赖中的未提交改动。
3. 只收集这些关联文件的 `git diff`。
4. **调用配置的 LLM API** 总结脚本变动。
5. 自动执行 `git commit --only`，避免把无关的已暂存或未暂存文件带进实验快照。

这确保了每一次实验运行都严格对应一个明确的代码版本，且拥有可读的历史记录。

## 🔧 高级配置

### 多服务器共享数据

将 `database.path` 指向共享存储（如 NFS）：

```yaml
database:
  path: "/mnt/nfs/labpilot/shared.db"
```

### ntfy 通知

```yaml
notification:
  active: [ntfy]
  ntfy:
    topic: "my-secret-topic"
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

### 通过 PushPlus / WxPusher 推送至个人微信

这两个服务都通过微信公众号把消息推送到你的**个人微信**，无需群机器人。

```yaml
notification:
  active: [pushplus]  # 或 wxpusher
  pushplus:
    token: "your-pushplus-token"  # 在 pushplus.plus 扫码后获取
    template: "markdown"
  wxpusher:
    app_token: "your-app-token"  # 来自 wxpusher.zjiecode.com
    uids: ["uid_xxxxx"]          # 扫码后获得的 uid
```

- **PushPlus** — 每天免费 200 条消息，支持 markdown 模板。配置：在 pushplus.plus 扫描二维码，复制你的 token。
- **WxPusher** — 支持富文本 HTML，可按个人或主题推送。配置：在 wxpusher.zjiecode.com 创建应用，分享二维码，收集 uids。

### 通过 OpenClaw 推送至个人微信（ClawBot 插件）

适用于已部署 **OpenClaw** 实例并绑定 **ClawBot** 插件的用户（腾讯官方个人微信 iLink 协议，2026/03/22 发布）：

```yaml
notification:
  active: [openclaw]
  openclaw:
    cli_path: "openclaw"          # 或绝对路径
    user_id: "your-wechat-user-id"
    timeout: 10
```

前置条件：Node.js 22+、`npm i -g openclaw@latest`、微信 iOS ≥ 8.0.70 / Android ≥ 8.0.69，在「我 → 设置 → 插件」中启用 ClawBot。该插件正在分批灰度，并非所有账号都已获得权限。

### 通过 QQ 推送（OneBot，自建机器人）

通过自建的 OneBot v11 实现向 QQ 账号或群发送消息。`qq` 与 `onebot` 均为合法的 `active:` 名称。

```yaml
notification:
  active: [qq]  # 或 [onebot]
  qq:
    base_url: "http://127.0.0.1:5700"   # 你的 OneBot v11 HTTP 端点
    access_token: "your-access-token"    # 在机器人中配置的 bearer token
    user_id: "123456789"                 # 私信目标（群消息则省略）
    group_id: "987654321"                # 群消息目标（私信则省略）
    auto_escape: true                    # 将消息以纯文本渲染
```

前置条件：自建的 Lagrange.OneBot 或 go-cqhttp 实例，暴露 OneBot v11 HTTP API。`base_url` 仅允许 `http`/`https` 且主机名非空（自建场景允许 localhost/127.0.0.1）。

### MiniMax Token Plan API

建议在 shell 中设置 `LABPILOT_AI_API_KEY` 或 `MINIMAX_API_KEY`，而不是把真实 token 写进配置文件。Dashboard API 提供一个脱敏配置检查接口：

```bash
GET /ai/token-plan
```

### 显卡检测和自动选择

LabPilot 自动检测可用的 NVIDIA GPU 并提供智能 GPU 排队功能：

**显存格式示例：**
- `12g` = 12 GB
- `10240m` = 10240 MB
- `any` = 任何可用的 GPU

**工作原理：**
1. 使用 `nvidia-smi` 查询 GPU 显存状态
2. 找到空闲显存足够的 GPU
3. 自动设置 `CUDA_VISIBLE_DEVICES` 环境变量
4. 等待直到合适的 GPU 可用

**命令示例：**
```bash
# 等待空闲显存 >8GB 的 GPU
labrun --wait-gpu 8g python train.py

# 等待空闲显存 >16384MB 的 GPU
labrun --wait-gpu 16384m python train.py

# 不等待 GPU 直接运行（使用默认 GPU）
labrun python train.py

# 结合超时设置使用
labrun --wait-gpu 12g --timeout 3600 python train.py
```

## 📊 JSON API / 仪表板后端

启动内置的 JSON API 后端查看实验历史（当前仅提供 JSON 接口，未挂载 HTML/静态资源路由）：

```bash
# 不启用鉴权（仅本地使用）
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 启用 API Key 鉴权（暴露到网络时推荐）
export LABPILOT_API_KEY="$(openssl rand -hex 32)"
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

仪表板读取的 SQLite 数据库与 CLI 写入的是同一个。接口 schema 见下方的 API 端点表；一旦设置了 `LABPILOT_API_KEY`，所有写端点都要求携带 `X-API-Key: <key>`（或 `Authorization: Bearer <key>`）。

### API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET`  | `/`                       | 存活探针 |
| `GET`  | `/ai/token-plan`          | 脱敏后的 AI 提供商配置（不含密钥） |
| `GET`  | `/experiments`            | 列出实验（支持 `?status=`、`?server=`、`?search=`、`?skip=`、`?limit=`） |
| `POST` | `/experiments`            | 插入一条新的 `running` 实验 |
| `GET`  | `/experiments/{id}`       | 获取单条实验 |
| `PUT`  | `/experiments/{id}`       | 更新实验（end_time、status、log_snippet 等） |
| `DELETE` | `/experiments/{id}`     | 硬删除一条实验 |
| `GET`  | `/experiments/stats`      | 聚合统计（总数、按状态、按服务器、最近 24 小时） |

## 🛡️ 安全

- **API Key 鉴权**（v2.2.0+）：`LABPILOT_API_KEY` 环境变量对所有读写操作进行鉴权。比较使用 `hmac.compare_digest`。默认安全——未设置 key 时所有写操作返回 401，读操作保持开放以便本地使用。**警告：若将仪表板暴露到网络且未设置 `LABPILOT_API_KEY`，所有读端点将处于无保护状态，强烈建议务必设置该 key。**
- **Webhook 重试**（v2.2.0+）：JSON webhook 通知器对瞬时网络错误和 5xx 响应进行指数退避重试，4xx 永不重试。
- **Webhook URL 白名单**（v2.2.0+）：钉钉 / 飞书 / 企业微信 / ntfy 的 webhook URL 均校验 scheme（`https`；自建的 ntfy / OneBot 允许 `http`）与固定主机名白名单，防止 SSRF 与凭据泄露。
- **子进程超时**（v2.1.0+）：每次 `subprocess.run` 都带有 `timeout=30 s`，避免卡死的 `git` 或 `nvidia-smi` 无限阻塞 `labrun`。
- **SQLite 韧性**（v2.2.0+）：每个连接都以 WAL 模式打开并设置 5 秒 busy 超时。labrun 并发写入与仪表板读取现在可以安全共存。
- **OpenClaw `cli_path`** 限定为 basename 以 `openclaw` 开头且磁盘上存在的可执行文件；`user_id` 若以 `-` 开头或包含空白字符则被拒绝（防止参数注入）。
- **WxPusher `base_url`** 仅允许 `wxpusher.zjiecode.com`（防止 SSRF 滥用）。
- **PushPlus 端点** 硬编码为 HTTPS（请求体携带用户的 PushPlus token）。

## 🧪 开发

```bash
# 运行测试套件
python -m pytest

# 带覆盖率（60 % 门槛）
python -m pytest  # 已通过 pyproject.toml 配置好

# Lint
ruff check .
ruff format --check .

# 类型检查
mypy labpilot/labpilot labpilot/api
```

每次推送都会通过 `.github/workflows/ci.yml` 运行 CI（lint + typecheck + tests，覆盖 Ubuntu + Windows × Python 3.9 – 3.12）。
