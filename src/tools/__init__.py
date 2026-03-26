"""
Tools module for tokindle
提供数据库、Kindle、文件管理等共享方法
"""
from .database import (
    load_database,
    save_database,
    get_file_info,
    update_file_info,
    delete_file_from_db
)
from .kindle import (
    check_kindle_connected,
    get_kindle_files,
    copy_to_kindle,
    delete_from_kindle,
    format_name
)
from .file_manager import (
    list_all_files,
    get_file_detail,
    delete_file_complete,
    search_files_by_keyword
)

__all__ = [
    # database
    'load_database',
    'save_database',
    'get_file_info',
    'update_file_info',
    'delete_file_from_db',
    # kindle
    'check_kindle_connected',
    'get_kindle_files',
    'copy_to_kindle',
    'delete_from_kindle',
    'format_name',
    # file_manager
    'list_all_files',
    'get_file_detail',
    'delete_file_complete',
    'search_files_by_keyword'
]