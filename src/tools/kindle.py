"""
Kindle 设备操作工具
包括连接检测、文件推送、删除等功能
"""
import re
import shutil
from pathlib import Path
from typing import Tuple, List, Set

from src.config import OUTPUT_FOLDER, KINDLE_ARTICLE_PATH as _INIT_KINDLE_PATH
from src.tools.database import get_file_info

# 模块级变量，可被 config.set_kindle_path() 动态更新
KINDLE_ARTICLE_PATH = _INIT_KINDLE_PATH


def check_kindle_connected() -> bool:
    """检查墨水屏阅读器是否连接

    Returns:
        True 如果设备已连接
    """
    return KINDLE_ARTICLE_PATH.exists()


def get_kindle_files() -> Set[str]:
    """获取墨水屏阅读器中已有的 KFX/EPUB 文件列表（不带扩展名）

    Returns:
        文件名集合（不含扩展名）
    """
    if not check_kindle_connected():
        return set()

    kindle_files = set()
    try:
        # 获取所有 .kfx 和 .epub 文件
        for ext in ['*.kfx', '*.epub']:
            for f in KINDLE_ARTICLE_PATH.glob(ext):
                kindle_files.add(f.stem)
    except Exception as e:
        print(f"获取墨水屏阅读器文件列表失败：{e}")
    return kindle_files


def format_name(name: str, max_length: int = 100) -> str:
    """格式化文件名为墨水屏阅读器兼容格式

    Args:
        name: 原始文件名
        max_length: 最大长度限制

    Returns:
        格式化后的文件名
    """
    # 移除扩展名
    name = Path(name).stem
    # 替换特殊字符
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # 替换连续空格为单个空格
    name = re.sub(r'\s+', ' ', name)
    # 去除首尾空格
    name = name.strip()
    # 限制长度
    if len(name) > max_length:
        name = name[:max_length]
    if not name:
        name = "unnamed"
    return name


def copy_to_kindle(file_id: str, file_type: str = 'kfx') -> Tuple[bool, str]:
    """将 KFX 或 EPUB 文件复制到墨水屏阅读器

    Args:
        file_id: 文件ID
        file_type: 'kfx' 或 'epub'，指定推送的文件类型

    Returns:
        (success, message): 成功标志和消息
    """
    if not check_kindle_connected():
        return False, "墨水屏阅读器未连接"

    info = get_file_info(file_id)
    if not info:
        return False, "文件不存在"

    # 使用数据库记录的文件名（original_name 去掉扩展名）
    original_name = info.get('name', '')
    if not original_name:
        return False, "文件名无效"

    # 格式化文件名为墨水屏阅读器兼容格式
    file_name = format_name(original_name)

    kfx_path = OUTPUT_FOLDER / f"{file_id}.kfx"
    epub_path = OUTPUT_FOLDER / f"{file_id}.epub"

    if file_type == 'kfx':
        if not kfx_path.exists():
            return False, "KFX 文件不存在"
        try:
            dest_kfx = KINDLE_ARTICLE_PATH / f"{file_name}.kfx"
            shutil.copy2(kfx_path, dest_kfx)
            print(f"Copied: {kfx_path} -> {dest_kfx}")
            return True, "KFX 推送成功"
        except Exception as e:
            print(f"Copy KFX to device failed: {e}")
            return False, f"KFX 复制失败：{str(e)}"
    else:  # epub
        if not epub_path.exists():
            return False, "EPUB 文件不存在"
        try:
            dest_epub = KINDLE_ARTICLE_PATH / f"{file_name}.epub"
            shutil.copy2(epub_path, dest_epub)
            print(f"Copied: {epub_path} -> {dest_epub}")
            return True, "EPUB 推送成功"
        except Exception as e:
            print(f"Copy EPUB to device failed: {e}")
            return False, f"EPUB 复制失败：{str(e)}"


def delete_from_kindle(file_id: str) -> Tuple[bool, str, List[str]]:
    """从墨水屏阅读器删除 KFX/EPUB 文件及相关 SDR 文件夹

    Args:
        file_id: 文件ID

    Returns:
        (success, message, deleted_items): 成功标志、消息、已删除项目列表
    """
    if not check_kindle_connected():
        return False, "墨水屏阅读器未连接", []

    info = get_file_info(file_id)
    if not info:
        return False, "文件不存在", []

    original_name = info.get('name', '')
    if not original_name:
        return False, "文件名无效", []

    # 格式化文件名为墨水屏阅读器兼容格式（与复制时保持一致）
    file_name = format_name(original_name)

    try:
        deleted_items = []

        # 删除 KFX 文件
        kfx_path = KINDLE_ARTICLE_PATH / f"{file_name}.kfx"
        if kfx_path.exists():
            kfx_path.unlink()
            deleted_items.append(f"{file_name}.kfx")
            print(f"Deleted: {kfx_path}")

        # 删除 KFX 的 SDR 文件夹（精确匹配：file_name.sdr）
        kfx_sdr_path = KINDLE_ARTICLE_PATH / f"{file_name}.sdr"
        if kfx_sdr_path.exists():
            shutil.rmtree(kfx_sdr_path)
            deleted_items.append(f"{file_name}.sdr")
            print(f"Deleted SDR: {kfx_sdr_path}")

        # 删除 file_id.sdr 文件夹（如果存在）
        sdr_path = KINDLE_ARTICLE_PATH / f"{file_id}.sdr"
        if sdr_path.exists():
            shutil.rmtree(sdr_path)
            deleted_items.append(f"{file_id}.sdr")
            print(f"Deleted SDR: {sdr_path}")

        # 删除可能存在的 EPUB 文件
        epub_path = KINDLE_ARTICLE_PATH / f"{file_name}.epub"
        if epub_path.exists():
            epub_path.unlink()
            deleted_items.append(f"{file_name}.epub")
            print(f"Deleted: {epub_path}")

        # 删除以 file_name_ 开头的 SDR 文件夹（阅读器生成的 {书名}_{唯一 ID}.sdr 格式）
        try:
            sdr_prefix = f"{file_name}_"
            for sdr_dir in KINDLE_ARTICLE_PATH.iterdir():
                if sdr_dir.is_dir() and sdr_dir.name.startswith(sdr_prefix) and sdr_dir.name.endswith('.sdr'):
                    shutil.rmtree(sdr_dir)
                    deleted_items.append(sdr_dir.name)
                    print(f"Deleted SDR (prefix match): {sdr_dir}")
        except Exception as e:
            print(f"Error scanning SDR folders: {e}")

        print(f"Deleted from device: {deleted_items}")
        return True, f"删除成功，共删除 {len(deleted_items)} 个项目", deleted_items
    except Exception as e:
        print(f"Delete from device failed: {e}")
        return False, f"删除失败：{str(e)}", []