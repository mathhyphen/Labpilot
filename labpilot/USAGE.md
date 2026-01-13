# LabPilot 使用文档

## 1. 项目简介

LabPilot 是一个轻量级的实验管理工具，专为深度学习研究者设计。它可以自动记录实验、集成 Git 版本控制、发送手机通知，并提供 Web 仪表板来跟踪您的实验。

### 核心功能

- **自动实验跟踪**：记录每个实验的命令、参数、时间、状态等
- **Git 集成**：自动快照当前代码版本
- **手机通知**：通过钉钉机器人实现实验状态实时推送
- **Web 仪表板**：直观展示所有实验状态
- **模型关联**：自动记录模型文件路径
- **多服务器支持**：管理多个服务器上的实验
- **灵活超时设置**：可配置实验超时时间，支持长时间运行的实验

## 2. 系统要求

- Linux/Windows/macOS 操作系统
- Python 3.7+
- Git
- SQLite3

## 3. 安装步骤

### 3.1 从源码安装

```bash
# 克隆项目
git clone https://github.com/yourusername/labpilot.git
cd labpilot

# 安装依赖
pip install -r requirements.txt

# 从源码安装
pip install -e .
```

### 3.2 从本地打包安装

```bash
# 构建包
python setup.py sdist bdist_wheel

# 安装打包好的文件
pip install dist/labpilot-1.0.0.tar.gz
```

安装完成后，您可以直接使用 `labrun` 命令。

## 4. 配置说明

### 4.1 配置文件

LabPilot 支持多种配置方式，优先级从高到低依次为：
1. 当前目录下的 `.labpilot.yaml`
2. 用户主目录下的 `~/.labpilot.yaml`
3. 项目目录下的 `config.yaml`

### 4.2 配置选项

```yaml
# 通知配置 - 钉钉机器人
notification:
  dingtalk:
    # 钉钉群聊机器人配置
    webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=your-token"  # 钉钉机器人Webhook URL
    timeout: 5  # 请求超时时间（秒）
    secret: "your-secret"  # 可选，加签密钥

# 数据库配置
database:
  path: "./labpilot.db"  # 数据库文件路径，支持绝对路径

# 日志配置
logging:
  level: "INFO"  # 日志级别
  max_log_lines: 20  # 保存到数据库的最大日志行数

# Git 配置
git:
  auto_snapshot: true  # 是否自动快照未提交的更改
  require_clean: false  # 是否要求仓库干净才能运行实验

# 超时配置
timeout:
  default: 0  # 默认超时时间（秒），0 表示无超时
```

### 4.3 钉钉机器人配置

钉钉机器人配置可以将通知发送到指定的钉钉群聊，配置简单，使用方便。

#### 4.3.1 配置步骤

1. **打开钉钉群聊**：
   - 打开钉钉客户端，进入你想要接收通知的群聊

2. **添加钉钉机器人**：
   - 点击群聊右上角的「...」
   - 选择「智能群助手」
   - 点击「添加机器人」
   - 选择「自定义」机器人
   - 点击「添加」

3. **配置机器人**：
   - 填写机器人名称（如：LabPilot通知）
   - 上传机器人头像（可选）
   - 选择安全设置：
     - **方式1：自定义关键词**：添加「LabPilot」、「实验」等关键词
     - **方式2：加签**：复制生成的密钥到配置文件的 `secret` 字段
     - **方式3：IP地址（段）**：添加你的服务器IP地址
   - 点击「完成」

4. **获取Webhook URL**：
   - 机器人添加成功后，会生成一个Webhook URL
   - 复制该URL到配置文件的 `webhook_url` 字段

5. **配置LabPilot**：
   - 将获取的Webhook URL填入配置文件中
   - 如果使用了加签，同时填写 `secret` 字段
   - 保存配置文件

#### 4.3.2 测试钉钉机器人通知

使用以下命令测试钉钉机器人通知：

```bash
# 运行一个简单的测试命令
labrun echo "测试钉钉机器人通知"
```

如果配置正确，你将收到钉钉通知，显示实验开始和结束信息。

#### 4.3.3 钉钉机器人Webhook URL格式

```
https://oapi.dingtalk.com/robot/send?access_token=your-unique-token
```

#### 4.3.4 注意事项

- 钉钉机器人每分钟最多发送20条消息
- 请勿将Webhook URL泄露给他人，否则可能导致恶意发送消息
- 根据选择的安全设置，确保消息符合要求：
  - 如果选择了自定义关键词，消息中必须包含至少一个关键词
  - 如果选择了加签，必须在发送消息时使用密钥进行签名
  - 如果选择了IP地址，必须确保发送请求的IP在白名单中

### 4.4 环境变量支持

您也可以通过环境变量覆盖配置：

```bash
# 设置钉钉机器人Webhook URL
LABPILOT_NOTIFICATION_DINGTALK_WEBHOOK_URL="https://oapi.dingtalk.com/robot/send?access_token=your-token" labrun python train.py

# 设置钉钉机器人加签密钥
LABPILOT_NOTIFICATION_DINGTALK_SECRET="your-secret" labrun python train.py

# 设置数据库路径
LABPILOT_DB_PATH="/path/to/labpilot.db" labrun python train.py
```

## 5. 使用方法

### 5.1 `labrun` 命令

`labrun` 是 LabPilot 的核心命令，用于运行实验并记录相关信息。

#### 5.1.1 基本语法

```bash
labrun <command> [args...]
```

#### 5.1.2 示例用法

```bash
# 运行 Python 脚本
labrun python train.py --config config.yaml --epochs 100 --gpu 0

# 运行 Shell 脚本
labrun ./train_script.sh --param1 value1 --param2 value2

# 运行无超时的实验
labrun --timeout 0 python long_running_experiment.py

# 运行10天超时的实验
labrun --timeout 864000 python very_long_experiment.py
```

#### 5.1.3 命令选项

| 选项 | 说明 |
|------|------|
| `-h, --help` | 显示帮助信息 |
| `--timeout TIMEOUT` | 实验超时时间（秒），0 表示无超时 |

## 6. Web 仪表板

### 6.1 启动 Web 服务

```bash
# 启动 FastAPI 服务
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

或者使用 Docker：

```bash
# 构建 Docker 镜像
docker build -t labpilot .

# 运行容器
docker run -p 8000:8000 -v $(pwd)/labpilot.db:/app/labpilot.db labpilot
```

访问 `http://your-server-ip:8000` 查看 Web 仪表板。

### 6.2 仪表板功能

- 查看所有实验的历史记录
- 按状态、服务器或关键字过滤实验
- 查看实验详情（命令、参数、日志片段等）
- 实时统计信息

## 7. 多服务器支持

### 7.1 集中式数据库配置

要管理多个服务器上的实验，您需要将所有服务器配置为使用同一个数据库文件。

1. **选择一个集中式存储位置**：
   - 可以使用网络共享存储（如 NFS、SMB）
   - 或者使用一个固定服务器上的数据库文件

2. **在所有服务器上配置相同的数据库路径**：
   ```yaml
   database:
     path: "/path/to/shared/labpilot.db"  # 共享存储上的数据库路径
   ```

3. **确保文件权限正确**：
   ```bash
   # 确保所有服务器都有读写权限
   chmod 666 /path/to/shared/labpilot.db
   ```

### 7.2 服务器标识

LabPilot 会自动获取服务器名称并在实验记录中包含该信息：
- 每个实验都会关联到其运行的服务器
- Web 仪表板中可以按服务器筛选和查看实验
- 通知中包含服务器名称，便于区分不同服务器上的实验

## 8. 灵活超时设置

### 8.1 配置默认超时

在 `config.yaml` 中设置默认超时时间：

```yaml
timeout:
  default: 86400  # 24小时（秒），设置为 0 表示无超时
```

### 8.2 临时覆盖超时

使用 `--timeout` 参数临时覆盖超时设置：

```bash
# 运行5小时超时的实验
labrun --timeout 18000 python train.py --epochs 100

# 运行无超时的实验
labrun --timeout 0 python long_running_experiment.py

# 运行10天超时的实验
labrun --timeout 864000 python very_long_experiment.py
```

### 8.3 超时行为

- 超时时间为 0 时，实验将一直运行直到完成
- 超时时间为正数时，实验将在指定时间后自动终止
- 超时终止的实验将返回退出码 124
- 超时信息会记录在实验日志中

## 9. 常见问题

### 9.1 没有收到钉钉机器人通知

**可能原因**：
- 钉钉机器人Webhook URL配置不正确
- 消息内容不符合安全设置要求
- 服务器IP未添加到IP白名单中
- 网络连接问题
- 机器人发送频率超过限制

**解决方法**：
1. **检查配置文件**：
   - 确认webhook_url是否正确，包含完整的access_token
   - 如果使用了加签，确认secret是否正确

2. **检查安全设置**：
   - 如果选择了「自定义关键词」，确保消息中包含至少一个关键词
   - 如果选择了「加签」，确保配置了正确的secret
   - 如果选择了「IP地址」，确保服务器IP已添加到白名单中

3. **检查网络连接**：
   - 确保服务器可以访问 `oapi.dingtalk.com`
   - 可以使用 `ping oapi.dingtalk.com` 测试网络连接

4. **测试Webhook URL**：
   ```bash
   curl -H "Content-Type: application/json" -d '{"msgtype": "text", "text": {"content": "测试通知"}}' https://oapi.dingtalk.com/robot/send?access_token=your-token
   ```

5. **检查发送频率**：
   - 钉钉机器人每分钟最多发送20条消息
   - 确保发送频率未超过限制

6. **检查群聊设置**：
   - 确保机器人已添加到对应的群聊
   - 确保机器人未被禁用

### 9.2 钉钉机器人通知发送失败，提示「关键字不匹配」

**可能原因**：
- 选择了「自定义关键词」安全设置，但消息中不包含任何关键词

**解决方法**：
- 在机器人安全设置中添加合适的关键词
- 确保发送的消息中包含至少一个关键词
- 或切换到其他安全设置方式

### 9.3 钉钉机器人通知发送失败，提示「签名不匹配」

**可能原因**：
- 选择了「加签」安全设置，但未正确配置secret

**解决方法**：
- 确保配置文件中的secret与机器人设置中的密钥一致
- 检查secret是否包含多余的空格或换行符
- 或切换到其他安全设置方式

### 9.4 实验未记录到数据库

**可能原因**：
- 数据库路径配置不正确
- 没有写入数据库的权限
- SQLite 版本不兼容

**解决方法**：
- 检查配置文件中的数据库路径是否正确
- 确保当前用户有写入数据库文件的权限
- 升级 SQLite 到最新版本

### 9.3 Web 仪表板无法访问

**可能原因**：
- FastAPI 服务未启动
- 端口被占用
- 防火墙设置问题

**解决方法**：
- 确保 FastAPI 服务已启动：`uvicorn api.main:app --host 0.0.0.0 --port 8000`
- 检查端口是否被占用：`lsof -i :8000`
- 检查防火墙设置，确保 8000 端口已开放：`sudo ufw allow 8000`

## 10. 最佳实践

### 10.1 命名约定

为了便于管理和搜索实验，建议您：
- 使用清晰、描述性的命令和参数
- 在命令中包含实验名称或标识符
- 使用一致的参数命名方式

### 10.2 配置管理

- 将敏感信息（如 ntfy 认证凭据）存储在 `~/.labpilot.yaml` 中，而不是版本控制系统中
- 为不同的项目创建不同的配置文件
- 定期备份数据库文件

### 10.3 实验组织

- 为每个实验系列创建单独的目录
- 使用版本控制管理实验配置文件
- 定期清理不再需要的实验记录

### 10.4 通知设置

- 为不同的项目或实验系列使用不同的钉钉机器人
- 根据实验重要性调整通知内容的详细程度
- 定期检查通知设置，确保能收到重要通知
- 选择合适的安全设置方式，平衡安全性和便利性
- 定期更新机器人密钥，确保安全性

## 11. 开发指南

### 11.1 项目结构

```
labpilot/
├── api/                 # FastAPI 服务
│   └── main.py          # API 主文件
├── labpilot/            # 核心 Python 模块
│   ├── web/             # Web 界面资源
│   │   ├── static/      # 静态资源
│   │   └── templates/   # HTML 模板
│   ├── cli.py           # 命令行接口
│   ├── database.py      # 数据库操作
│   ├── git_utils.py     # Git 集成
│   └── notify.py        # 通知功能
├── Dockerfile           # Docker 构建文件
├── MANIFEST.in          # 打包配置
├── README.md            # 项目文档
├── config.yaml          # 配置文件模板
├── requirements.txt     # Python 依赖
└── setup.py             # 包安装配置
```

### 11.2 开发流程

1. 克隆项目
2. 安装依赖：`pip install -r requirements.txt`
3. 运行测试：`python -m pytest`
4. 开发新功能
5. 构建包：`python setup.py sdist bdist_wheel`

## 12. 许可证

LabPilot 采用 MIT 许可证，详见 LICENSE 文件。

## 13. 联系方式

如有任何问题或建议，请通过以下方式联系：

- GitHub Issues：https://github.com/yourusername/labpilot/issues
- 邮件：labpilot@example.com

---

**版本**: 1.0.0  
**最后更新**: 2026-01-08