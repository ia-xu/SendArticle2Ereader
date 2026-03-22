"""
项目配置文件
"""
from pathlib import Path

# 基础目录
BASE_DIR = Path(__file__).parent.parent

# 上传和输出目录
UPLOAD_FOLDER = BASE_DIR / 'uploads'
OUTPUT_FOLDER = BASE_DIR / 'outputs'
DATABASE_FILE = BASE_DIR / 'database.json'

# Kindle 配置
KINDLE_ARTICLE_PATH = Path("E:/documents/Downloads/Items01/article")

# Cookie 文件路径
ZHIHU_COOKIE_FILE = BASE_DIR / 'config' / 'zhihu_cookies.json'
WECHAT_COOKIE_FILE = BASE_DIR / 'config' / 'wechat_cookies.json'

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'md', 'markdown'}

# 任务管理配置
MAX_WORKERS = 3  # 最多并发任务数
TASK_MAX_AGE_HOURS = 24  # 任务保留时间（小时）

PORT = 5006