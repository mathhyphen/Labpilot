"""
LabPilot Git 工具模块
处理 Git 相关操作
"""

import subprocess
import os
import yaml
import requests
import json
from typing import Tuple, Optional

import time

class GitUtils:
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.git_config = self.config.get('git', {})
        self.ai_config = self.config.get('ai', {})

    def _load_config(self, config_path: Optional[str] = None):
        """加载配置文件"""
        config_paths = []
        
        if config_path:
            config_paths.append(config_path)
        
        config_paths.extend([
            os.path.join(os.getcwd(), ".labpilot.yaml"),
            os.path.expanduser("~/.labpilot.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        ])
        
        config = {}
        for path in config_paths:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                break
        
        # 设置默认值
        if not config:
            config = {
                'git': {
                    'auto_snapshot': True,
                    'require_clean': False
                }
            }
        
        return config
    
    def is_git_repo(self) -> bool:
        """检查当前目录是否为 Git 仓库"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_git_info(self) -> Tuple[str, str]:
        """获取 Git 信息 (commit_hash, commit_message)"""
        if not self.is_git_repo():
            return "not-a-git-repo", "not-a-git-repo"
        
        try:
            # 获取当前 commit hash
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            commit_hash = result.stdout.strip() if result.returncode == 0 else "unknown"
            
            # 获取 commit message
            result = subprocess.run(
                ['git', 'log', '-1', '--pretty=%s'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            commit_message = result.stdout.strip() if result.returncode == 0 else "unknown"
            
            return commit_hash, commit_message
        except Exception:
            return "unknown", "unknown"
    
    def is_dirty(self) -> bool:
        """检查 Git 仓库是否有未提交的更改"""
        if not self.is_git_repo():
            return False
        
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            return len(result.stdout.strip()) > 0
        except Exception:
            return False
    
    def get_diff(self) -> str:
        """获取 Git 差异"""
        if not self.is_git_repo():
            return ""
        
        try:
            # 获取暂存区差异
            result_staged = subprocess.run(
                ['git', 'diff', '--cached'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            
            # 获取工作区差异
            result_working = subprocess.run(
                ['git', 'diff'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            
            diff = ""
            if result_staged.returncode == 0:
                diff += result_staged.stdout
            if result_working.returncode == 0:
                diff += result_working.stdout
                
            return diff
        except Exception:
            return ""

    def generate_ai_commit_message(self, diff: str) -> Optional[str]:
        """使用 AI 生成提交信息"""
        if not diff or not self.ai_config:
            return None
            
        api_key = self.ai_config.get('api_key')
        base_url = self.ai_config.get('base_url', 'https://open.bigmodel.cn/api/paas/v4/')
        model = self.ai_config.get('model', 'glm-4')
        
        if not api_key:
            return None
            
        # 限制 Diff 长度，防止超过 token 限制
        max_len = 3000
        if len(diff) > max_len:
            diff = diff[:max_len] + "\n... (truncated)"
            
        # 获取超时设置，默认为 120 秒
        timeout = self.ai_config.get('timeout', 120)

        prompt = f"""
        请根据以下代码变动（git diff），生成一个简洁明了的 git commit message。
        格式要求：
        1. 第一行：简短的总结（不超过 50 个字符）
        2. 第二行：空行
        3. 第三行开始：详细的改动说明
        
        代码变动：
        {diff}
        """
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个专业的代码提交助手。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        
        try:
            # 处理 base_url，确保它指向 /chat/completions
            if not base_url.endswith('/chat/completions'):
                if base_url.endswith('/'):
                    url = f"{base_url}chat/completions"
                else:
                    url = f"{base_url}/chat/completions"
            else:
                url = base_url
            
            # 添加重试机制
            max_retries = 3
            retry_delay = 2  # 初始等待2秒
            
            for attempt in range(max_retries):
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result['choices'][0]['message']['content']
                        return content.strip()
                    elif response.status_code == 429:
                        if attempt < max_retries - 1:
                            print(f"[WARN] AI API Rate Limit (429). Retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # 指数退避
                            continue
                        else:
                            print(f"[ERROR] AI API Rate Limit (429) after {max_retries} retries: {response.text}")
                            return None
                    else:
                        print(f"[ERROR] AI API Error: {response.status_code} - {response.text}")
                        return None
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    if attempt < max_retries - 1:
                        print(f"[WARN] AI API Network Error ({type(e).__name__}). Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    raise
                    
            return None
                
        except Exception as e:
            print(f"[WARN] AI Request Failed (timeout={timeout}s): {e}")
            return None

    def auto_commit(self, message: str = None, specific_files: Optional[list] = None) -> str:
        """自动提交更改"""
        if not self.is_git_repo():
            return "not-a-git-repo"
        
        if not self.is_dirty():
            # 仓库干净，返回当前 commit hash
            commit_hash, _ = self.get_git_info()
            return commit_hash
        
        # 如果未指定消息，尝试使用 AI 生成
        if message is None:
            # 1. 添加更改到暂存区，以便获取完整的 diff
            try:
                if specific_files:
                    subprocess.run(['git', 'add'] + specific_files, check=True, cwd=os.getcwd())
                else:
                    subprocess.run(['git', 'add', '.'], check=True, cwd=os.getcwd())
            except subprocess.CalledProcessError:
                pass
                
            # 2. 获取 Diff
            diff = self.get_diff()
            
            # 3. 尝试生成 AI 消息
            ai_message = self.generate_ai_commit_message(diff)
            
            if ai_message:
                message = ai_message
            else:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                message = f"Auto-snapshot before experiment run [labpilot-{timestamp}]"
        
        try:
            # 确保再次添加（如果之前没添加成功，或者防止某些情况）
            if specific_files:
                subprocess.run(['git', 'add'] + specific_files, check=True, cwd=os.getcwd())
            else:
                subprocess.run(['git', 'add', '.'], check=True, cwd=os.getcwd())
            
            # 提交更改
            subprocess.run(['git', 'commit', '-m', message], check=True, cwd=os.getcwd())
            
            # 获取新 commit hash
            commit_hash, _ = self.get_git_info()
            
            return commit_hash
        except subprocess.CalledProcessError:
            # 如果提交失败，返回当前 commit hash
            commit_hash, _ = self.get_git_info()
            return commit_hash
    
    def check_and_handle_repo(self, specific_files: Optional[list] = None) -> str:
        """检查并处理仓库状态"""
        if not self.is_git_repo():
            return "not-a-git-repo"
        
        is_dirty = self.is_dirty()
        
        if is_dirty and self.git_config.get('require_clean', False):
            raise Exception("Git repository has uncommitted changes and git.require_clean is true")
        
        if is_dirty and self.git_config.get('auto_snapshot', True):
            return self.auto_commit(specific_files=specific_files)
        else:
            commit_hash, _ = self.get_git_info()
            return commit_hash
    
    def get_commit_body(self) -> str:
        """获取完整的 commit message"""
        if not self.is_git_repo():
            return "not-a-git-repo"
        
        try:
            # 获取完整 commit message (subject + body)
            result = subprocess.run(
                ['git', 'log', '-1', '--pretty=%B'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"


# 全局 Git 工具实例
_git_utils_instance = None


def get_git_utils(config_path: Optional[str] = None) -> GitUtils:
    """获取 Git 工具实例"""
    global _git_utils_instance
    if _git_utils_instance is None:
        _git_utils_instance = GitUtils(config_path)
    return _git_utils_instance