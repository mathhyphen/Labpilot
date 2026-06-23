"""
LabPilot CLI 模块
提供 labrun 命令的实现
"""

import argparse
import logging
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from typing import Optional

from .config import load_config as _load_unified_config
from .git_utils import GitRequireCleanError, get_git_utils
from .notify import get_notifier

logger = logging.getLogger(__name__)


def load_config(config_path: Optional[str] = None):
    """加载配置文件 (仅用于 CLI 初始化其他组件，通知器内部自己加载)。

    Thin wrapper around :func:`labpilot.config.load_config` kept for
    backwards compatibility — the optional ``config_path`` argument
    lets callers force a specific file.
    """
    if config_path is not None:
        return _load_unified_config(explicit_path=config_path)
    return _load_unified_config()


def extract_params(args):
    """从命令行参数中提取参数"""
    params = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("-"):
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                # 参数有值
                params.append(f"{arg} {args[i + 1]}")
                i += 2
            else:
                # 参数无值（标志）
                params.append(arg)
                i += 1
        else:
            i += 1

    return " ".join(params)


def extract_ckpt_path(log_content: str) -> str:
    """从日志中提取最后一个模型/检查点路径。

    Review finding H3: the previous implementation captured only the
    two groups ``(checkpoint, pth)`` and reassembled ``"checkpoint.pth"``,
    throwing away the actual filename (``42``, ``final``, ``best_ema``).
    We now capture the whole path-like token.

    Strategy: find the last run of path-shaped characters
    (``\\w``, ``/``, ``.``, ``-``) that ends in a model-file
    extension. The "no spaces in the path" constraint matches the
    reality of model save APIs (PyTorch, HF, etc.) which always emit
    the full path on one line.
    """
    pattern = r"[\w./-]+\.(?:pth|pt|ckpt|bin|safetensors)"
    matches = re.findall(pattern, log_content, re.IGNORECASE)
    if not matches:
        return ""
    # The last match is typically the final saved model.
    return matches[-1]


def parse_memory_str(mem_str):
    """解析显存大小字符串，返回 MB 整数"""
    mem_str = str(mem_str).lower().strip()
    if mem_str == "any":
        return 0

    multiplier = 1
    if mem_str.endswith("g") or mem_str.endswith("gb"):
        multiplier = 1024
        mem_str = mem_str.rstrip("gb")
    elif mem_str.endswith("m") or mem_str.endswith("mb"):
        multiplier = 1
        mem_str = mem_str.rstrip("mb")

    try:
        return int(float(mem_str) * multiplier)
    except ValueError:
        return 0


def safe_kill_process(process: subprocess.Popen) -> None:
    """Kill a subprocess, swallowing only expected OS errors.

    The previous bare ``except:`` also caught ``KeyboardInterrupt`` and
    ``SystemExit`` (effectively making the wrapper unkillable). We narrow
    the catch to ``(ProcessLookupError, OSError)`` so that real signals
    propagate to the caller. ``ProcessLookupError`` covers the case
    where the child has already exited; ``OSError`` is its parent class
    on POSIX/Windows for other kernel-level failures.
    """
    try:
        process.kill()
    except (ProcessLookupError, OSError):
        pass


def get_free_gpus(min_memory_mb: int) -> list:
    """获取满足显存要求的空闲 GPU 索引列表"""
    try:
        # 查询所有 GPU 的剩余显存
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        gpus = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            idx, free_mem = line.split(",")
            if int(free_mem) >= min_memory_mb:
                gpus.append(int(idx))

        return gpus
    except FileNotFoundError:
        # 没有 nvidia-smi，可能是非 GPU 机器
        return []
    except Exception as e:
        logger.warning("检查 GPU 状态失败: %s", e)
        return []


def wait_for_gpu(
    wait_arg,
    notifier=None,
    server_name="unknown",
    command_str="",
    commit_hash="",
    timeout: int = 0,
):
    """Wait until a suitable GPU becomes available.

    Args:
        wait_arg: Memory string (e.g. ``"12g"``, ``"10240m"``, ``"any"``).
        notifier: Optional notifier to ping when the wait completes.
        server_name, command_str, commit_hash: Reserved for the
            future "we started waiting" notification (not sent today).
        timeout: Maximum seconds to wait. ``0`` means "no limit" —
            preserves the historical "wait forever" behaviour for
            callers that pass ``timeout=0`` explicitly. Otherwise the
            function returns ``None`` if no GPU frees up in time.

    Implementation notes (review findings H8 + H1):

      * The pre-fix code called ``time.sleep(30)`` once per poll,
        which made Ctrl+C take up to 30 s to propagate. We now
        sleep in 0.5 s sub-ticks so signals land promptly.
      * The pre-fix code ignored ``--timeout`` and waited forever.
        The new ``timeout`` argument is checked every sub-tick.
    """
    min_mem = parse_memory_str(wait_arg)
    logger.info("正在等待可用 GPU (要求显存 > %d MB)...", min_mem)

    spinner = ["|", "/", "-", "\\"]
    idx = 0
    start = time.monotonic()
    sub_tick = 0.5  # seconds — keep small so Ctrl+C is prompt

    while True:
        available_gpus = get_free_gpus(min_mem)

        if available_gpus:
            chosen_gpu = available_gpus[0]
            logger.info("资源就绪! 使用 GPU %d", chosen_gpu)

            # 关键：强制 CUDA 使用 PCI 总线顺序，确保与 nvidia-smi 索引一致
            os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
            os.environ["CUDA_VISIBLE_DEVICES"] = str(chosen_gpu)
            logger.info(
                "设置 CUDA_VISIBLE_DEVICES=%d (CUDA_DEVICE_ORDER=PCI_BUS_ID)",
                chosen_gpu,
            )

            if notifier:
                # 占位：未来在这里发"GPU 就绪"通知
                pass

            return chosen_gpu

        # Check timeout (skip when timeout=0 == "no limit").
        if timeout > 0 and (time.monotonic() - start) >= timeout:
            logger.warning(
                "等待 GPU 超时 (>%d 秒)，放弃。",
                timeout,
            )
            return None

        # 状态输出
        sys.stdout.write(f"\r[LabPilot] {spinner[idx]} 暂无满足要求的空闲显卡，等待中...")
        sys.stdout.flush()
        idx = (idx + 1) % len(spinner)

        time.sleep(sub_tick)


def main():
    """主函数 - labrun 命令的入口点"""
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="LabPilot - AI 实验管理与通知中心")
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="实验超时时间（秒），0 表示无超时，默认为配置文件中的设置",
    )
    parser.add_argument(
        "--wait-gpu",
        type=str,
        default=None,
        help='等待直到有显存满足要求的显卡可用 (例如: "12g", "10240m", "any")',
    )
    parser.add_argument("command", nargs="+", help="要执行的命令及参数")

    # 解析命令行参数
    args, remaining = parser.parse_known_args()

    # 解析配置
    config = load_config()
    db_path = config.get("database", {}).get("path", "./labpilot.db")

    # 确定超时时间
    default_timeout = config.get("timeout", {}).get("default", 86400)  # 默认24小时
    timeout = args.timeout if args.timeout is not None else default_timeout

    # 初始化数据库连接
    from .database import get_db

    db = get_db(db_path)

    # 获取命令参数
    command = args.command + remaining
    command_str = " ".join(command)

    # 初始化 Git 工具
    git_utils = get_git_utils()

    # 初始化通知器
    notifier = get_notifier()

    # 自动排队/等待 GPU
    if args.wait_gpu:
        # Pass the experiment timeout (in seconds) so the wait gives
        # up at the same deadline as the run itself. (Review H8.)
        wait_for_gpu(args.wait_gpu, timeout=timeout)

    # 尝试提取脚本文件作为特定的提交文件
    specific_files = []

    # 检测 Python 脚本和 Shell 脚本
    script_file = None
    for arg in command:
        if (arg.endswith(".py") or arg.endswith(".sh")) and os.path.exists(arg):
            script_file = arg
            break

    if script_file:
        specific_files = git_utils.get_related_dirty_files(script_file)
        if specific_files:
            logger.info(
                "将只自动提交入口脚本及关联改动: %s",
                ", ".join(specific_files),
            )

    # 自动处理 Git 快照和检查
    try:
        # 只有当找到了特定的脚本文件时，才进行自动提交
        if specific_files:
            git_utils.check_and_handle_repo(specific_files=specific_files)
        else:
            # 如果没找到脚本，且不是强制要求 clean，则跳过自动快照，避免意外提交其他文件
            # 但仍需获取当前 commit hash (如果有的)
            if config.get("git", {}).get("require_clean", False):
                # 如果要求 clean 但没找到脚本，按理说应该检查整个 repo？
                # 为了安全起见，还是调用 check_and_handle_repo 但不传文件，让它去检查 dirty
                # 注意：git_utils.check_and_handle_repo 内部如果没有 specific_files 会提交所有
                # 所以这里我们需要小心。
                # 如果没找到脚本，我们只做检查，不提交？
                # 暂时维持原状：只在有脚本时提交。没脚本时，不提交。
                pass

            # 记录日志提示用户
            # print("[LabPilot] 未检测到脚本文件，跳过 Git 自动快照。")
            pass

    except GitRequireCleanError as e:
        # git.require_clean 为 True 且仓库有未提交改动：终止实验。
        logger.error("Git 仓库不干净，require_clean 终止实验: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Git 错误: %s", e)

    # 获取 Git 信息
    commit_hash, _ = git_utils.get_git_info()
    commit_message = git_utils.get_commit_body()

    # 提取参数
    params = extract_params(command)

    # 获取服务器信息：优先配置，其次 platform.node()（跨平台，
    # os.uname 在 Windows 上不存在，旧实现会抛 AttributeError）。
    server_name = config.get("server_name") or platform.node() or "unknown"

    # 插入初始实验记录（持久化 server_name 与 commit_message）
    experiment_id = db.insert_experiment(
        command_str,
        commit_hash,
        params,
        "running",
        server_name=server_name,
        commit_message=commit_message,
    )

    # 发送开始通知
    notifier.send_start_notification(server_name, command_str, commit_hash)

    # 执行命令
    start_epoch = time.time()
    log_content = ""
    exit_code = 0

    try:
        # 使用临时文件捕获输出
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_log:
            temp_log_path = temp_log.name

            # 执行命令并捕获输出
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # 读取线程：把 stdout 行持续读入 buffer，EOF 时放入哨兵。
            # 这样主线程永远不会阻塞在 readline() 上 —— 即便子进程
            # 挂死且不产出任何输出，--timeout 仍能可靠触发（旧实现
            # 在 readline() 上阻塞，导致超时检查形同虚设）。
            lines_buffer: list = []
            EOF_SENTINEL = object()

            def _drain_stdout() -> None:
                try:
                    for line in process.stdout:
                        lines_buffer.append(line)
                except Exception as e:  # noqa: BLE001
                    logger.warning("读取子进程输出失败: %s", e)
                finally:
                    lines_buffer.append(EOF_SENTINEL)

            reader_thread = threading.Thread(target=_drain_stdout, daemon=True)
            reader_thread.start()

            timed_out = False
            saw_eof = False
            while not saw_eof:
                # 取走读线程已缓冲的全部行。
                while lines_buffer:
                    item = lines_buffer.pop(0)
                    if item is EOF_SENTINEL:
                        saw_eof = True
                        break
                    print(item, end="")
                    temp_log.write(item)
                    log_content += item

                if saw_eof:
                    break

                # 超时检查：子进程静默挂死时仍能生效，因为阻塞在
                # stdout 上的只有读线程，主线程在此处照常轮询。
                if timeout > 0 and (time.time() - start_epoch) > timeout:
                    safe_kill_process(process)
                    timed_out = True
                    log_content += f"\n\n实验超时 ({timeout}秒) 被终止\n"
                    break

                # poll() 回收已退出的子进程；读线程会在 stdout 关闭
                # 后投递 EOF。短睡眠避免 CPU 空转。
                process.poll()
                time.sleep(0.5)

            # 等待进程完成，并让读线程收尾。
            process.wait()
            reader_thread.join(timeout=2)
            exit_code = process.returncode

            if timed_out:
                exit_code = 124  # 使用124表示超时（参考timeout命令）

    except KeyboardInterrupt:
        if "process" in locals() and process.poll() is None:
            safe_kill_process(process)
        if "reader_thread" in locals():
            reader_thread.join(timeout=2)
        exit_code = 130
        log_content += "\n\n实验被用户中断 (Ctrl+C)\n"
        logger.info("实验被用户中断 (Ctrl+C)")

    except Exception as e:
        exit_code = 1
        log_content = str(e)

    end_epoch = time.time()
    end_time = datetime.now().isoformat()
    duration = end_epoch - start_epoch

    # 获取日志片段
    log_lines = log_content.split("\n")
    log_snippet = "\n".join(log_lines[-config.get("logging", {}).get("max_log_lines", 20) :])
    log_snippet = log_snippet[:500]  # 限制长度

    # 提取模型路径
    ckpt_path = extract_ckpt_path(log_content)

    # 确定状态
    status = "success" if exit_code == 0 else "failed"

    # 更新实验记录
    db.update_experiment(
        experiment_id, end_time, duration, status, log_snippet, exit_code, ckpt_path
    )

    # 格式化时长
    duration_hms = f"{int(duration // 3600)}h {int((duration % 3600) // 60)}m {int(duration % 60)}s"

    # 发送结束通知
    if exit_code == 0:
        notifier.send_success_notification(
            server_name, command_str, commit_hash, duration_hms, ckpt_path, log_snippet
        )
    elif exit_code == 130:
        notifier.send_abort_notification(
            server_name, command_str, commit_hash, duration_hms, log_snippet
        )
    else:
        # 获取错误片段（通常是日志的最后几行）
        error_snippet = log_snippet
        notifier.send_failure_notification(
            server_name, command_str, commit_hash, exit_code, duration_hms, error_snippet
        )

    # 退出码
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
