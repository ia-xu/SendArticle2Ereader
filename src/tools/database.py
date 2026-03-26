"""
数据库操作工具
管理 database.json 的读写操作

数据库结构：
{
    "files": {
        "file_id": { file_info }
    }
}
"""
import json
from pathlib import Path
from src.config import DATABASE_FILE


def load_database() -> dict:
    """加载数据库

    Returns:
        完整数据库字典，包含 'files' 键
    """
    if DATABASE_FILE.exists():
        try:
            with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)
                # 确保有 files 键
                if 'files' not in db:
                    db['files'] = {}
                return db
        except Exception:
            return {'files': {}}
    return {'files': {}}


def save_database(db: dict):
    """保存数据库

    Args:
        db: 完整数据库字典
    """
    with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def get_file_info(file_id: str) -> dict:
    """获取文件信息

    Args:
        file_id: 文件ID

    Returns:
        文件信息字典，不存在返回 None
    """
    db = load_database()
    return db.get('files', {}).get(file_id)


def update_file_info(file_id: str, info: dict):
    """更新文件信息

    Args:
        file_id: 文件ID
        info: 要更新的信息（会合并到现有信息中）
    """
    db = load_database()
    if 'files' not in db:
        db['files'] = {}
    if file_id not in db['files']:
        db['files'][file_id] = {}
    db['files'][file_id].update(info)
    save_database(db)


def delete_file_from_db(file_id: str):
    """从数据库删除文件记录

    Args:
        file_id: 文件ID
    """
    db = load_database()
    if 'files' in db and file_id in db['files']:
        del db['files'][file_id]
        save_database(db)