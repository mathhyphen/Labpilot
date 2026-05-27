"""
LabPilot Git 工具模块
处理 Git 相关操作
"""

import subprocess
import os
import yaml
import requests
import json
import ast
from typing import Tuple, Optional, List, Set

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

    def get_dirty_files(self) -> List[str]:
        """获取当前 Git 工作区中有改动的文件路径。"""
        if not self.is_git_repo():
            return []

        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            if result.returncode != 0:
                return []

            files = []
            for line in result.stdout.splitlines():
                if not line.strip():
                    continue
                path = line[3:].strip()
                if ' -> ' in path:
                    path = path.split(' -> ', 1)[1].strip()
                if path:
                    files.append(path.replace('\\', '/'))
            return files
        except Exception:
            return []

    def get_related_dirty_files(self, script_file: str) -> List[str]:
        """只返回入口脚本及其本地 Python 依赖中已修改的文件。"""
        dirty_files = set(self.get_dirty_files())
        if not dirty_files:
            return []

        related_files = self._collect_local_python_dependencies(script_file)
        related_files.add(os.path.relpath(script_file, os.getcwd()).replace('\\', '/'))
        return sorted(path for path in related_files if path in dirty_files)

    def _collect_local_python_dependencies(self, script_file: str) -> Set[str]:
        """静态解析入口脚本导入的本地 Python 文件。"""
        root = os.getcwd()
        visited = set()
        related = set()

        def relpath(path: str) -> str:
            return os.path.relpath(path, root).replace('\\', '/')

        def resolve_module(module_name: str, base_dir: str) -> Optional[str]:
            if not module_name:
                return None

            parts = module_name.split('.')
            candidates = [
                os.path.join(base_dir, *parts) + '.py',
                os.path.join(root, *parts) + '.py',
                os.path.join(base_dir, *parts, '__init__.py'),
                os.path.join(root, *parts, '__init__.py'),
            ]
            root_abs = os.path.abspath(root)
            for candidate in candidates:
                candidate_abs = os.path.abspath(candidate)
                if os.path.exists(candidate_abs) and os.path.commonpath([root_abs, candidate_abs]) == root_abs:
                    return candidate_abs
            return None

        def visit(path: str):
            abs_path = os.path.abspath(path)
            if abs_path in visited or not abs_path.endswith('.py') or not os.path.exists(abs_path):
                return

            visited.add(abs_path)
            related.add(relpath(abs_path))

            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read())
            except Exception:
                return

            base_dir = os.path.dirname(abs_path)
            for node in ast.walk(tree):
                module_names = []
                if isinstance(node, ast.Import):
                    module_names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    module_names.append(node.module)

                for module_name in module_names:
                    module_path = resolve_module(module_name, base_dir)
                    if module_path:
                        visit(module_path)

        visit(script_file)
        return related
    
    def get_diff(self, specific_files: Optional[list] = None) -> str:
        """获取 Git 差异"""
        if not self.is_git_repo():
            return ""
        
        try:
            # 构造命令基础
            cmd_staged = ['git', 'diff', '--cached']
            cmd_working = ['git', 'diff']
            
            # 如果指定了文件，只获取这些文件的差异
            if specific_files:
                cmd_staged.extend(specific_files)
                cmd_working.extend(specific_files)
            
            # 获取暂存区差异
            result_staged = subprocess.run(
                cmd_staged,
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            
            # 获取工作区差异
            result_working = subprocess.run(
                cmd_working,
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
            
        api_key = self._get_ai_setting('api_key', env_names=['LABPILOT_AI_API_KEY', 'MINIMAX_API_KEY'])
        base_url = self._get_ai_setting('base_url', 'https://api.minimaxi.com/v1')
        model = self._get_ai_setting('model', 'MiniMax-M2.7-highspeed')
        
        if not api_key:
            return None
            
        # 限制 Diff 长度，防止超过 token 限制
        max_len = int(self._get_ai_setting('max_diff_chars', 3000))
        if len(diff) > max_len:
            diff = diff[:max_len] + "\n... (truncated)"
            
        # 获取超时设置，默认为 120 秒
        timeout = self._get_ai_setting('timeout', 120)
        
        # 获取语言设置，默认为中文
        language = self._get_ai_setting('language', 'zh-CN')
        lang_instruction = "请使用简体中文回复。" if language == 'zh-CN' else f"Please respond in {language}."

        prompt = f"""
        {lang_instruction}
        请根据以下入口脚本及其关联脚本的 git diff，生成一个简洁明了的 git commit message。
        格式要求：
        1. 第一行：简短总结，不超过 50 个字符，建议使用 conventional commit 风格
        2. 第二行：空行
        3. 第三行开始：总结脚本行为或实验逻辑的关键变动
        
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

    def _get_ai_setting(self, key: str, default=None, env_names: Optional[List[str]] = None):
        """从环境变量或配置文件读取 AI 设置，环境变量优先。"""
        for env_name in env_names or []:
            value = os.getenv(env_name)
            if value:
                return value

        env_name = f"LABPILOT_AI_{key.upper()}"
        value = os.getenv(env_name)
        if value:
            return value

        return self.ai_config.get(key, default)

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
            diff = self.get_diff(specific_files=specific_files)
            
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
            
            # 提交更改；指定文件时忽略其他已暂存内容，避免带入无关改动。
            commit_cmd = ['git', 'commit', '-m', message]
            if specific_files:
                commit_cmd.extend(['--only', '--'])
                commit_cmd.extend(specific_files)
            subprocess.run(commit_cmd, check=True, cwd=os.getcwd())
            
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
