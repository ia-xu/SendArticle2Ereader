"""
项目配置文件
"""
from pathlib import Path
import json

# 基础目录
BASE_DIR = Path(__file__).parent.parent

# 上传和输出目录
UPLOAD_FOLDER = BASE_DIR / 'uploads'
OUTPUT_FOLDER = BASE_DIR / 'outputs'
DATABASE_FILE = BASE_DIR / 'database.json'

# 用户配置文件
USER_CONFIG_FILE = BASE_DIR / 'user_config.json'

# 默认用户配置
DEFAULT_USER_CONFIG = {
    'enable_epub_support': True  # 是否启用 EPUB 支持
}

def load_user_config():
    """加载用户配置"""
    if USER_CONFIG_FILE.exists():
        try:
            with open(USER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 合并默认配置
                return {**DEFAULT_USER_CONFIG, **config}
        except:
            pass
    return DEFAULT_USER_CONFIG.copy()

def save_user_config(config):
    """保存用户配置"""
    with open(USER_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# 阅读器配置
KINDLE_ARTICLE_PATH = Path("F:/documents/Downloads/Items01/article")
# KINDLE_ARTICLE_PATH = Path(r'Z:\documents\Downloads\Items01\article')
# Cookie 文件路径
ZHIHU_COOKIE_FILE = BASE_DIR / 'config' / 'zhihu_cookies.json'
WECHAT_COOKIE_FILE = BASE_DIR / 'config' / 'wechat_cookies.json'

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'md', 'markdown'}

# 任务管理配置
MAX_WORKERS = 3  # 最多并发任务数
TASK_MAX_AGE_HOURS = 24  # 任务保留时间（小时）

PORT = 5006