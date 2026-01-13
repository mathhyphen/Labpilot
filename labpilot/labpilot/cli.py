"""
LabPilot CLI 模块
提供 labrun 命令的实现
"""

import sys
import os
import subprocess
import sqlite3
import json
import time
import argparse
from datetime import datetime
import yaml
import requests
import tempfile
import re
from .git_utils import get_git_utils
from .notify import get_notifier


def load_config():
    """加载配置文件 (仅用于 CLI 初始化其他组件，通知器内部自己加载)"""
    # 这里其实可以使用 notify.py 中的 _load_config_data 逻辑，或者保留这个为了 database 等其他模块
    # 为了减少代码重复，最好统一，但现在我们先保持 CLI 的独立性，只需确保配置路径逻辑一致
    config_paths = [
        os.path.join(os.getcwd(), ".labpilot.yaml"),
        os.path.expanduser("~/.labpilot.yaml"),
        os.path.join(os.path.dirname(__file__), "config.yaml")
    ]
    
    config = {}
    for path in config_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            break
    
    if not config:
        config = {} # 返回空字典，让各模块使用默认值
        
    return config


def extract_params(args):
    """从命令行参数中提取参数"""
    params = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith('-'):
            if i + 1 < len(args) and not args[i + 1].startswith('-'):
                # 参数有值
                params.append(f"{arg} {args[i + 1]}")
                i += 2
            else:
                # 参数无值（标志）
                params.append(arg)
                i += 1
        else:
            i += 1
    
    return ' '.join(params)


def extract_ckpt_path(log_content):
    """从日志中提取模型路径"""
    # 常见的模型文件扩展名
    pattern = r'(checkpoint|model|save|output).*?\.(pth|pt|ckpt|bin|safetensors)'
    matches = re.findall(pattern, log_content, re.IGNORECASE)
    
    if matches:
        # 返回最后一个匹配项（通常是最终保存的模型）
        return matches[-1][0] + '.' + matches[-1][1]
    
    return ""


def main():
    """主函数 - labrun 命令的入口点"""
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='LabPilot - AI 实验管理与通知中心')
    parser.add_argument('--timeout', type=int, default=None, 
                        help='实验超时时间（秒），0 表示无超时，默认为配置文件中的设置')
    parser.add_argument('command', nargs='+', 
                        help='要执行的命令及参数')
    
    # 解析命令行参数
    args, remaining = parser.parse_known_args()
    
    # 解析配置
    config = load_config()
    db_path = config.get('database', {}).get('path', './labpilot.db')
    
    # 确定超时时间
    default_timeout = config.get('timeout', {}).get('default', 86400)  # 默认24小时
    timeout = args.timeout if args.timeout is not None else default_timeout
    
    # 初始化数据库连接
    from .database import get_db
    db = get_db(db_path)
    
    # 获取命令参数
    command = args.command + remaining
    command_str = ' '.join(command)
    
    # 初始化 Git 工具
    git_utils = get_git_utils()
    
    # 初始化通知器
    notifier = get_notifier()
    
    # 尝试提取脚本文件作为特定的提交文件
    specific_files = []
    
    # 检测 Python 脚本
    script_file = None
    for arg in command:
        if arg.endswith('.py') and os.path.exists(arg):
            script_file = arg
            break
            
    if script_file:
        specific_files.append(script_file)
    
    # 自动处理 Git 快照和检查
    try:
        # 如果找到了特定的脚本文件，则只提交该文件
        if specific_files:
            git_utils.check_and_handle_repo(specific_files=specific_files)
        else:
            git_utils.check_and_handle_repo()
    except Exception as e:
        print(f"[ERROR] Git 错误: {e}")
        # 如果要求仓库干净但检查失败，则终止实验
        if "require_clean" in str(e):
            sys.exit(1)
            
    # 获取 Git 信息
    commit_hash, _ = git_utils.get_git_info()
    commit_message = git_utils.get_commit_body()
    
    # 提取参数
    params = extract_params(command)
    
    # 获取服务器信息
    # 优先从配置中读取
    server_name = config.get('server_name')
    
    # 如果配置中没有，尝试从系统中获取
    if not server_name:
        if hasattr(os, 'uname'):
            server_name = os.uname().nodename
        else:
            import platform
            server_name = platform.node()
            
    if not server_name:
        server_name = 'unknown'
    
    # 插入初始实验记录
    experiment_id = db.insert_experiment(command_str, commit_hash, params, "running")
    
    # 发送开始通知
    notifier.send_start_notification(server_name, command_str, commit_hash)
    
    # 执行命令
    start_epoch = time.time()
    log_content = ""
    exit_code = 0
    
    try:
        # 使用临时文件捕获输出
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_log:
            temp_log_path = temp_log.name
            
            # 执行命令并捕获输出
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # 实时读取输出并写入临时文件和标准输出
            timed_out = False
            while True:
                # 检查是否超时
                if timeout > 0:
                    elapsed = time.time() - start_epoch
                    if elapsed > timeout:
                        process.kill()
                        timed_out = True
                        log_content += f"\n\n实验超时 ({timeout}秒) 被终止\n"
                        break
                
                # 读取输出
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    print(line, end='')
                    temp_log.write(line)
                    log_content += line
                else:
                    # 没有输出，短暂休眠避免CPU占用过高
                    time.sleep(0.1)
            
            # 等待进程完成
            process.wait()
            exit_code = process.returncode
            
            if timed_out:
                exit_code = 124  # 使用124表示超时（参考timeout命令）
            
    except Exception as e:
        exit_code = 1
        log_content = str(e)
    
    end_epoch = time.time()
    end_time = datetime.now().isoformat()
    duration = end_epoch - start_epoch
    
    # 获取日志片段
    log_lines = log_content.split('\n')
    log_snippet = '\n'.join(log_lines[-config.get('logging', {}).get('max_log_lines', 20):])
    log_snippet = log_snippet[:500]  # 限制长度
    
    # 提取模型路径
    ckpt_path = extract_ckpt_path(log_content)
    
    # 确定状态
    status = "success" if exit_code == 0 else "failed"
    
    # 更新实验记录
    db.update_experiment(
        experiment_id, end_time, duration, status, 
        log_snippet, exit_code, ckpt_path
    )
    
    # 格式化时长
    duration_hms = f"{int(duration//3600)}h {int((duration%3600)//60)}m {int(duration%60)}s"
    
    # 发送结束通知
    if exit_code == 0:
        notifier.send_success_notification(
            server_name, command_str, commit_hash, duration_hms, ckpt_path, log_snippet
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
