"""
文件管理工具
包括文件列表、详情查看、删除、搜索等功能
"""
import shutil
from pathlib import Path
from typing import List, Dict, Optional

from src.config import UPLOAD_FOLDER, OUTPUT_FOLDER, KINDLE_ARTICLE_PATH
from src.tools.database import (
    load_database,
    get_file_info,
    delete_file_from_db
)
from src.tools.kindle import (
    check_kindle_connected,
    get_kindle_files,
    format_name,
    delete_from_kindle
)


def list_all_files(
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50
) -> List[Dict]:
    """列出所有文件

    Args:
        status: 按状态过滤（uploaded, converted, converted_epub）
        source: 按来源过滤（zhihu, wechat, arxiv, upload）
        limit: 返回结果的最大数量（0 表示不限制）

    Returns:
        文件信息列表
    """
    db = load_database()
    files = []

    for file_id, info in db.get('files', {}).items():
        # 过滤状态
        if status and info.get('status') != status:
            continue
        # 过滤来源
        if source and info.get('source') != source:
            continue

        item = {
            "file_id": file_id,
            "name": info.get('name', ''),
            "author": info.get('author', ''),
            "source": info.get('source', ''),
            "source_url": info.get('source_url', ''),
            "status": info.get('status', ''),
            "upload_time": info.get('upload_time', ''),
            "has_kfx": (OUTPUT_FOLDER / f"{file_id}.kfx").exists(),
            "has_epub": (OUTPUT_FOLDER / f"{file_id}.epub").exists(),
        }
        files.append(item)

    # 按上传时间倒序排列
    files.sort(key=lambda x: x.get('upload_time', ''), reverse=True)

    # 限制数量
    if limit > 0:
        files = files[:limit]

    return files


def get_file_detail(file_id: str) -> Optional[Dict]:
    """获取文件详情

    Args:
        file_id: 文件ID

    Returns:
        文件详细信息，不存在返回 None
    """
    info = get_file_info(file_id)
    if not info:
        return None

    kindle_files = get_kindle_files() if check_kindle_connected() else set()
    file_name = format_name(info.get('name', ''))
    on_kindle = file_name in kindle_files

    return {
        "file_id": file_id,
        "name": info.get('name', ''),
        "original_name": info.get('original_name', ''),
        "author": info.get('author', ''),
        "source": info.get('source', ''),
        "source_url": info.get('source_url', ''),
        "status": info.get('status', ''),
        "upload_time": info.get('upload_time', ''),
        "convert_time": info.get('convert_time', ''),
        "has_kfx": (OUTPUT_FOLDER / f"{file_id}.kfx").exists(),
        "has_epub": (OUTPUT_FOLDER / f"{file_id}.epub").exists(),
        "has_md": (UPLOAD_FOLDER / f"{file_id}.md").exists(),
        "on_kindle": on_kindle,
        "convert_error": info.get('convert_error')
    }


def search_files_by_keyword(keyword: str, check_kindle: bool = False) -> List[Dict]:
    """按关键字搜索文件

    Args:
        keyword: 搜索关键字，匹配文件标题
        check_kindle: 是否同时检查文件是否在 Kindle 上

    Returns:
        匹配的文件列表
    """
    db = load_database()
    results = []
    kindle_files = get_kindle_files() if check_kindle else None

    keyword_lower = keyword.lower()

    for file_id, info in db.get('files', {}).items():
        name = info.get('name', '')
        if keyword_lower in name.lower():
            item = {
                "file_id": file_id,
                "name": name,
                "author": info.get('author', ''),
                "source": info.get('source', ''),
                "status": info.get('status', ''),
                "has_kfx": (OUTPUT_FOLDER / f"{file_id}.kfx").exists(),
                "has_epub": (OUTPUT_FOLDER / f"{file_id}.epub").exists(),
            }

            if check_kindle and kindle_files is not None:
                file_name = format_name(name)
                item["on_kindle"] = file_name in kindle_files

            results.append(item)

    return results


def delete_file_complete(file_id: str, remove_from_kindle: bool = False) -> Dict:
    """完全删除文件（包括本地文件、数据库记录，可选删除 Kindle 上的文件）

    Args:
        file_id: 文件ID
        remove_from_kindle: 是否同时从 Kindle 删除

    Returns:
        操作结果字典
    """
    info = get_file_info(file_id)
    if not info:
        return {"success": False, "error": "文件不存在"}

    deleted_items = []

    # 删除本地文件
    for folder, exts in [(UPLOAD_FOLDER, ['.md']), (OUTPUT_FOLDER, ['.kfx', '.epub'])]:
        for ext in exts:
            file_path = folder / f"{file_id}{ext}"
            if file_path.exists():
                file_path.unlink()
                deleted_items.append(str(file_path))

    # 删除 images 目录
    images_dir = UPLOAD_FOLDER / f"{file_id}_images"
    if images_dir.exists():
        shutil.rmtree(images_dir)
        deleted_items.append(str(images_dir))

    # 从数据库删除
    delete_file_from_db(file_id)
    deleted_items.append(f"database entry: {file_id}")

    # 从 Kindle 删除
    kindle_deleted = []
    if remove_from_kindle:
        success, message, items = delete_from_kindle(file_id)
        kindle_deleted = items

    return {
        "success": True,
        "file_id": file_id,
        "deleted_from_system": deleted_items,
        "deleted_from_kindle": kindle_deleted,
        "message": f"已删除 {len(deleted_items)} 个文件"
    }