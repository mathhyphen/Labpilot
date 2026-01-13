# LabPilot - AI 实验管理与通知中心

LabPilot 是一个轻量级的实验管理工具，专为深度学习研究者设计。它可以自动记录实验、集成 Git 版本控制、发送手机通知，并提供 Web 仪表板来跟踪您的实验。

## 🚀 功能特性

- **自动实验跟踪**：记录每个实验的命令、参数、时间、状态等
- **Git 集成**：自动快照当前代码版本
- **手机通知**：通过 ntfy 实现实验状态实时推送
- **SQLite 数据库**：轻量级存储，支持集中式配置
- **Web 仪表板**：直观展示所有实验状态，支持多服务器筛选
- **模型关联**：自动记录模型文件路径
- **多服务器支持**：管理多个服务器上的实验，集中查看和分析
- **灵活超时设置**：可配置实验超时时间，支持长时间运行的实验

## 📋 系统要求

- Linux 服务器（推荐 Ubuntu 18.04+ 或 CentOS 7+）
- Python 3.7+
- Git
- curl
- SQLite3

## 🛠️ 安装步骤

### 1. 克隆或下载 LabPilot

```bash
# 如果您使用 Git
git clone https://github.com/yourusername/labpilot.git
cd labpilot

# 或者直接下载并解压
wget https://github.com/yourusername/labpilot/archive/main.zip
unzip main.zip
cd labpilot-main
```

### 2. 配置 ntfy 通知

编辑配置文件 `config.yaml`：

```yaml
ntfy:
  server: "https://ntfy.sh"  # 您的 ntfy 服务器地址
  topic: "labpilot-notifications"  # 您的 ntfy 主题
  username: ""  # 如果需要认证
  password: ""  # 如果需要认证
  timeout: 5

database:
  path: "./labpilot.db"

logging:
  level: "INFO"
  max_log_lines: 20

git:
  auto_snapshot: true
  require_clean: false

timeout:
  default: 86400  # 24小时（秒）
```

或者创建用户配置文件 `~/.labpilot.yaml`：

```bash
cp config.yaml ~/.labpilot.yaml
# 编辑 ~/.labpilot.yaml 以匹配您的设置
```

### 3. 设置 ntfy 通知

1. 访问 [ntfy.sh](https://ntfy.sh) 或部署自己的 ntfy 服务器
2. 选择一个主题名称（例如 `my-lab-experiments`）
3. 在手机上安装 ntfy 应用并订阅该主题
4. 更新配置文件中的 `topic` 字段

### 4. 使用 labrun 命令

不再使用 `python train.py`，而是使用：

```bash
# 基本用法
./labrun python train.py --lr 1e-4 --batch_size 32

# 带参数的用法
./labrun python train.py --config config.yaml --epochs 100 --gpu 0

# 运行任何命令
./labrun ./train_script.sh --param1 value1 --param2 value2
```

## 📊 Web 仪表板

### 启动 Web 服务

```bash
# 安装 Python 依赖
pip install -r requirements.txt

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

### 仪表板功能

- 查看所有实验的历史记录
- 按状态、服务器或关键字过滤实验
- 查看实验详情（命令、参数、日志片段等）
- 实时统计信息

## 🌐 多服务器支持

### 集中式数据库配置

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

### 服务器标识

LabPilot 会自动获取服务器名称并在实验记录中包含该信息：
- 每个实验都会关联到其运行的服务器
- Web 仪表板中可以按服务器筛选和查看实验
- 通知中包含服务器名称，便于区分不同服务器上的实验

### 多服务器最佳实践

1. **统一配置管理**：在所有服务器上使用相同的配置文件，确保通知设置一致
2. **定期备份**：定期备份共享数据库文件，防止数据丢失
3. **合理分配资源**：根据服务器性能分配不同类型的实验
4. **使用不同的通知主题**：可以为不同服务器配置不同的 ntfy 主题，便于区分通知

## ⏰ 灵活超时设置

### 配置默认超时

在 `config.yaml` 中设置默认超时时间：

```yaml
timeout:
  default: 86400  # 24小时（秒），设置为 0 表示无超时
```

### 临时覆盖超时

使用 `--timeout` 参数临时覆盖超时设置：

```bash
# 运行5小时超时的实验
labrun --timeout 18000 python train.py --epochs 100

# 运行无超时的实验
labrun --timeout 0 python long_running_experiment.py

# 运行10天超时的实验
labrun --timeout 864000 python very_long_experiment.py
```

### 超时行为

- 超时时间为 0 时，实验将一直运行直到完成
- 超时时间为正数时，实验将在指定时间后自动终止
- 超时终止的实验将返回退出码 124
- 超时信息会记录在实验日志中

## 🔧 高级功能

### Git 自动快照

LabPilot 会自动记录每次实验的 Git 状态：

- 如果仓库干净，记录当前 commit hash
- 如果仓库有修改且 `git.auto_snapshot` 为 `true`，则自动提交并打标签

### 模型文件跟踪

LabPilot 会自动检测并记录模型文件路径，方便后续查找。

### 超时保护

默认情况下，实验会在 24 小时后自动终止，防止无限运行。

## 📱 手机通知格式

### 实验开始
```
⏳ 实验开始
[gpu01] python train.py --lr 1e-4
Commit: a1b2c3d
```

### 实验成功
```
✅ 实验成功
[gpu01] python train.py --lr 1e-4
Commit: a1b2c3d
Duration: 2h 17m
Model: ./runs/exp01/model_best.pth
Log: val_acc=0.922, loss=0.231...
```

### 实验失败
```
❌ 实验失败
[gpu01] python train.py --lr 1e-4
Commit: a1b2c3d
Exit code: 1
Duration: 1h 32m
Error: CUDA out of memory...
```

## 🤖 与现有工作流集成

LabPilot 设计为零侵入性，您无需修改现有的训练脚本：

1. 保持现有的 `train.py` 不变
2. 将 `python train.py` 替换为 `./labrun python train.py`
3. 所有实验数据将自动记录和通知

### 示例使用

我们提供了一个示例训练脚本 `sample_train.py` 来演示如何使用 LabPilot：

```bash
# 基本使用
./labrun python sample_train.py --epochs 5 --lr 0.001

# 带参数的使用
./labrun python sample_train.py --epochs 10 --lr 0.01 --batch_size 64 --model_type complex

# 在实际项目中使用
./labrun python train.py --config config.yaml --epochs 100 --gpu 0
```

## 🧪 测试 LabPilot

运行以下命令来测试 LabPilot 安装：

```bash
# 运行内置测试
./launch.sh test

# 发送测试通知
./notify.sh test

# 使用示例脚本测试完整流程
./labrun python sample_train.py --epochs 3 --lr 0.001
```

## 📦 pip 安装（推荐方式）

您可以通过 pip 安装 LabPilot：

### 从源码安装

```bash
# 克隆项目
git clone https://github.com/yourusername/labpilot.git
cd labpilot

# 从源码安装
pip install -e .
```

### 从本地打包安装

```bash
# 构建包
python setup.py sdist bdist_wheel

# 安装打包好的文件
pip install dist/labpilot-1.0.0.tar.gz
```

安装完成后，您可以直接使用 `labrun` 命令而无需 ./ 前缀：

```bash
labrun python train.py --lr 1e-4 --batch_size 32
```

## ⚙️ 配置文件说明

LabPilot 支持多种配置方式，优先级从高到低依次为：
1. 当前目录下的 `.labpilot.yaml`
2. 用户主目录下的 `~/.labpilot.yaml`
3. 项目目录下的 `config.yaml`

### 完整配置选项

```yaml
# 服务器名称（可选）
server_name: "My-GPU-Server-01"

# ntfy 通知配置
ntfy:
  server: "https://ntfy.sh"  # ntfy 服务器地址
  topic: "labpilot-notifications"  # ntfy 主题
  username: ""  # 认证用户名（可选）
  password: ""  # 认证密码（可选）
  timeout: 5  # 通知超时时间（秒）

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
  default: 86400  # 默认超时时间（秒），0 表示无超时
```

### 环境变量支持

您也可以通过环境变量覆盖配置：

```bash
# 设置数据库路径
LABPILOT_DB_PATH="/path/to/labpilot.db" labrun python train.py
```

## 🔒 安全考虑

- 敏感信息（如 ntfy 认证凭据）应存储在 `~/.labpilot.yaml` 中，而不是版本控制系统中
- 确保数据库文件权限适当
- 在生产环境中使用 HTTPS 和身份验证

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进 LabPilot！

## 📄 许可证

MIT License

## 🆘 支持

如果遇到问题，请检查：

1. 确保所有依赖项都已安装
2. 检查配置文件路径和权限
3. 验证 ntfy 服务器连接
4. 查看日志文件获取更多信息

对于进一步的支持，请提交 GitHub Issue。