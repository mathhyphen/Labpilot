"""
LabPilot 数据库模块
处理实验数据的存储和检索
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional


class ExperimentDB:
    def __init__(self, db_path: str = None):
        # 如果没有提供路径，从配置中获取或使用默认值
        if db_path is None:
            from .cli import load_config
            config = load_config()
            db_path = config.get('database', {}).get('path', './labpilot.db')
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                server TEXT,
                command TEXT NOT NULL,
                commit_hash TEXT,
                commit_message TEXT,
                params TEXT,
                ckpt_path TEXT,
                duration REAL,
                status TEXT,
                log_snippet TEXT,
                exit_code INTEGER
            )
        """)
        
        conn.commit()
        conn.close()
    
    def insert_experiment(self, command: str, commit_hash: str = "", 
                         params: str = "", status: str = "running") -> int:
        """插入新的实验记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        start_time = datetime.now().isoformat()
        server = os.uname().nodename if hasattr(os, 'uname') else 'unknown'
        
        cursor.execute("""
            INSERT INTO experiments (start_time, server, command, commit_hash, params, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (start_time, server, command, commit_hash, params, status))
        
        experiment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return experiment_id
    
    def update_experiment(self, experiment_id: int, end_time: str, duration: float, 
                         status: str, log_snippet: str, exit_code: int, 
                         ckpt_path: str = ""):
        """更新实验记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE experiments 
            SET end_time=?, duration=?, status=?, log_snippet=?, exit_code=?, ckpt_path=?
            WHERE id=?
        """, (end_time, duration, status, log_snippet, exit_code, ckpt_path, experiment_id))
        
        conn.commit()
        conn.close()
    
    def get_experiment(self, experiment_id: int) -> Optional[Dict]:
        """获取单个实验记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            columns = [
                'id', 'start_time', 'end_time', 'server', 'command', 
                'commit_hash', 'commit_message', 'params', 'ckpt_path', 
                'duration', 'status', 'log_snippet', 'exit_code'
            ]
            return dict(zip(columns, row))
        return None
    
    def get_experiments(self, limit: int = 100, offset: int = 0, 
                       status: Optional[str] = None) -> List[Dict]:
        """获取实验列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM experiments"
        params = []
        
        if status:
            query += " WHERE status = ?"
            params.append(status)
        
        query += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        columns = [
            'id', 'start_time', 'end_time', 'server', 'command', 
            'commit_hash', 'commit_message', 'params', 'ckpt_path', 
            'duration', 'status', 'log_snippet', 'exit_code'
        ]
        
        return [dict(zip(columns, row)) for row in rows]
    
    def get_stats(self) -> Dict:
        """获取实验统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总实验数
        cursor.execute("SELECT COUNT(*) FROM experiments")
        total = cursor.fetchone()[0]
        
        # 按状态统计
        cursor.execute("SELECT status, COUNT(*) FROM experiments GROUP BY status")
        status_counts = dict(cursor.fetchall())
        
        # 按服务器统计
        cursor.execute("SELECT server, COUNT(*) FROM experiments WHERE server IS NOT NULL GROUP BY server")
        server_counts = dict(cursor.fetchall())
        
        # 最近24小时实验数
        cursor.execute("""
            SELECT COUNT(*) FROM experiments 
            WHERE start_time >= datetime('now', '-1 day')
        """)
        recent = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_experiments': total,
            'status_counts': status_counts,
            'server_counts': server_counts,
            'recent_experiments': recent
        }


# 全局数据库实例
_db_instance = None


def get_db(db_path: str = "./labpilot.db") -> ExperimentDB:
    """获取数据库实例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = ExperimentDB(db_path)
    return _db_instance