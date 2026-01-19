"""
LabPilot 通知模块
支持钉钉群聊机器人和 ntfy 通知
"""

import requests
import yaml
import os
import hmac
import hashlib
import base64
import time
from typing import Optional, Union


class BaseNotifier:
    """通知器基类"""
    def __init__(self, config=None):
        self.config = config or {}

    def send_notification(self, title: str, message: str, tags: str = "", priority: str = "default") -> bool:
        raise NotImplementedError

    def send_start_notification(self, server: str, command: str, commit_hash: str) -> bool:
        title = "⏳ 实验开始"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}"
        return self.send_notification(title, message, "hourglass_done", "default")

    def send_success_notification(self, server: str, command: str, commit_hash: str, 
                                duration: str, model_path: str = "", 
                                log_snippet: str = "") -> bool:
        title = "✅ 实验成功"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}\nDuration: {duration}"
        
        if model_path:
            message += f"\nModel: {model_path}"
        
        if log_snippet:
            message += f"\nLog: {log_snippet[:100]}..."
        
        return self.send_notification(title, message, "white_check_mark", "default")

    def send_failure_notification(self, server: str, command: str, commit_hash: str, 
                                exit_code: int, duration: str, 
                                error_snippet: str = "") -> bool:
        title = "❌ 实验失败"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}\nExit code: {exit_code}\nDuration: {duration}"
        
        if error_snippet:
            message += f"\nError: {error_snippet[:100]}..."
        
        return self.send_notification(title, message, "x", "high")

    def send_abort_notification(self, server: str, command: str, commit_hash: str, 
                                duration: str, log_snippet: str = "") -> bool:
        title = "🚫 实验中断"
        message = f"[{server}] {command}\nCommit: {commit_hash[:7]}\nDuration: {duration}"
        
        if log_snippet:
            message += f"\nLog: {log_snippet[:100]}..."
        
        return self.send_notification(title, message, "no_entry_sign", "high")

    def send_test_notification(self) -> bool:
        title = "LabPilot Test"
        message = "This is a test notification from LabPilot"
        return self.send_notification(title, message, "test", "default")


class DingTalkNotifier(BaseNotifier):
    """钉钉群聊机器人通知器"""
    def __init__(self, config):
        super().__init__(config)
        self.dingtalk_config = self.config.get('notification', {}).get('dingtalk', {})
    
    def send_notification(self, title: str, message: str, tags: str = "", 
                         priority: str = "default") -> bool:
        webhook_url = self.dingtalk_config.get('webhook_url', '')
        timeout = self.dingtalk_config.get('timeout', 5)
        secret = self.dingtalk_config.get('secret', '')
        
        if not webhook_url:
            # 静默失败，或者在此处打印错误，但通常由上层逻辑决定是否调用
            print("[ERROR] 钉钉机器人配置错误：webhook_url 未配置")
            return False
        
        # 处理加签
        final_url = webhook_url
        if secret:
            timestamp = str(int(time.time() * 1000))
            secret_enc = secret.encode('utf-8')
            string_to_sign = f'{timestamp}\n{secret}'.encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign, digestmod=hashlib.sha256).digest()
            sign = base64.b64encode(hmac_code).decode('utf-8')
            
            if '?' in final_url:
                final_url += f'&timestamp={timestamp}&sign={sign}'
            else:
                final_url += f'?timestamp={timestamp}&sign={sign}'
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"## {title}\n{message}"
            }
        }
        
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(
                final_url,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            result = response.json()
            if result.get('errcode') == 0:
                print(f"[SUCCESS] 钉钉机器人通知发送成功")
                return True
            else:
                print(f"[ERROR] 发送钉钉机器人通知失败: {result}")
                return False
        except Exception as e:
            print(f"[ERROR] 发送钉钉机器人通知时发生错误: {str(e)}")
            return False


class NtfyNotifier(BaseNotifier):
    """ntfy 通知器"""
    def __init__(self, config):
        super().__init__(config)
        self.ntfy_config = self.config.get('notification', {}).get('ntfy', {})

    def send_notification(self, title: str, message: str, tags: str = "", 
                         priority: str = "default") -> bool:
        server = self.ntfy_config.get('server', 'https://ntfy.sh')
        topic = self.ntfy_config.get('topic', '')
        username = self.ntfy_config.get('username', '')
        password = self.ntfy_config.get('password', '')
        timeout = self.ntfy_config.get('timeout', 5)

        if not topic:
            print("[ERROR] ntfy 配置错误：topic 未配置")
            return False

        url = f"{server}/{topic}"
        headers = {
            "Title": title,
            "Tags": tags,
            "Priority": priority
        }
        
        # Markdown 处理 - ntfy 支持 Markdown，但需要简单格式化
        # 这里直接发送文本内容
        
        auth = None
        if username and password:
            auth = (username, password)
            
        try:
            response = requests.post(
                url,
                data=message.encode('utf-8'),
                headers=headers,
                auth=auth,
                timeout=timeout
            )
            
            if response.status_code == 200:
                print(f"[SUCCESS] ntfy 通知发送成功")
                return True
            else:
                print(f"[ERROR] 发送 ntfy 通知失败: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"[ERROR] 发送 ntfy 通知时发生错误: {str(e)}")
            return False


class MultiNotifier(BaseNotifier):
    """组合通知器，支持同时发送多种通知"""
    def __init__(self, config, notifiers):
        super().__init__(config)
        self.notifiers = notifiers

    def send_notification(self, title: str, message: str, tags: str = "", priority: str = "default") -> bool:
        results = []
        for notifier in self.notifiers:
            results.append(notifier.send_notification(title, message, tags, priority))
        return any(results)


def _load_config_data(config_path: Optional[str] = None):
    """加载配置文件数据"""
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
            
    if not config:
        config = {
            'notification': {
                'dingtalk': {},
                'ntfy': {}
            }
        }
    return config


# 全局通知器实例
_notifier_instance = None


def get_notifier(config_path: Optional[str] = None) -> BaseNotifier:
    """获取通知器实例"""
    global _notifier_instance
    if _notifier_instance is None:
        config = _load_config_data(config_path)
        notification_config = config.get('notification', {})
        active_providers = notification_config.get('active', ['dingtalk'])
        
        # 兼容旧配置：如果没有 active 字段，检查 dingtalk webhook 是否存在
        if 'active' not in notification_config:
            if notification_config.get('dingtalk', {}).get('webhook_url'):
                active_providers = ['dingtalk']
            elif notification_config.get('ntfy', {}).get('topic'):
                active_providers = ['ntfy']
            else:
                active_providers = []

        # 如果 active 是字符串，转换为列表
        if isinstance(active_providers, str):
            active_providers = [active_providers]

        notifiers = []
        if 'dingtalk' in active_providers:
            notifiers.append(DingTalkNotifier(config))
        if 'ntfy' in active_providers:
            notifiers.append(NtfyNotifier(config))
            
        if len(notifiers) == 1:
            _notifier_instance = notifiers[0]
        elif len(notifiers) > 1:
            _notifier_instance = MultiNotifier(config, notifiers)
        else:
            # 默认返回 DingTalkNotifier 以保持行为一致（即使没配置，打印错误也好）
            _notifier_instance = DingTalkNotifier(config)
            
    return _notifier_instance
