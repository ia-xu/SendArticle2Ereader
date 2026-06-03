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

# 阅读器配置 - 默认路径，可通过 set_kindle_path() 动态修改
_DEFAULT_KINDLE_PATH = Path("F:/documents/Downloads/Items01/article")

# 启动时从 user_config.json 恢复上次保存的路径
_KINDLE_ARTICLE_PATH = Path(load_user_config().get('kindle_upload_path', str(_DEFAULT_KINDLE_PATH)))

def get_kindle_path() -> Path:
    """获取当前 Kindle 上传路径"""
    return _KINDLE_ARTICLE_PATH

def set_kindle_path(new_path: str) -> Path:
    """动态修改 Kindle 上传路径（无需重启 MCP）"""
    global _KINDLE_ARTICLE_PATH
    p = Path(new_path)
    # 确保路径存在
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
    _KINDLE_ARTICLE_PATH = p
    # 同步更新 kindle.py 模块中的引用
    import src.tools.kindle as _kindle_mod
    _kindle_mod.KINDLE_ARTICLE_PATH = p
    # 持久化到 user_config.json，重启后也能记住
    config = load_user_config()
    config['kindle_upload_path'] = str(p)
    save_user_config(config)
    return p

# 向后兼容：模块级属性 KINDLE_ARTICLE_PATH 也指向同一对象
KINDLE_ARTICLE_PATH = _KINDLE_ARTICLE_PATH
# Cookie 文件路径
ZHIHU_COOKIE_FILE = BASE_DIR / 'config' / 'zhihu_cookies.json'
WECHAT_COOKIE_FILE = BASE_DIR / 'config' / 'wechat_cookies.json'

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'md', 'markdown'}

# 任务管理配置
MAX_WORKERS = 3  # 最多并发任务数
TASK_MAX_AGE_HOURS = 24  # 任务保留时间（小时）

PORT = 5006