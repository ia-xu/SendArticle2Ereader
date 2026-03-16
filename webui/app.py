"""
Flask WebUI for Markdown to KFX Converter
"""
import os
import sys
import json
import shutil
import uuid
import hashlib
import zipfile
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from werkzeug.utils import secure_filename
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor


# 添加 src 目录到路径

from src.md2kfx import MarkdownToKFX

# 知乎下载器导入
ZHIHU_DOWNLOADER_PATH = Path(__file__).parent.parent / 'src' / ' downloader'
sys.path.insert(0, str(ZHIHU_DOWNLOADER_PATH))
try:
    from zhihu2markdown import ZhihuAuth, ZhihuToMarkdown, ZhihuClient
    ZHIHU_AVAILABLE = True
except ImportError as e:
    print(f"[Warning] Zhihu downloader not available: {e}")
    ZHIHU_AVAILABLE = False

# 微信下载器导入
try:
    from wechat2markdown import WeChatAuth, WeChatToMarkdown, WeChatClient
    WECHAT_AVAILABLE = True
except ImportError as e:
    print(f"[Warning] WeChat downloader not available: {e}")
    WECHAT_AVAILABLE = False

app = Flask(__name__)

# 后台任务管理器
class TaskManager:
    """后台任务管理器，用于管理异步下载和转换任务"""

    def __init__(self):
        self.tasks = {}  # task_id -> task_info
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=3)  # 最多3个并发任务

    def create_task(self, task_type, params):
        """创建新任务"""
        task_id = str(uuid.uuid4())[:8]
        with self.lock:
            self.tasks[task_id] = {
                'id': task_id,
                'type': task_type,
                'status': 'pending',
                'progress': 0,
                'message': '等待执行',
                'result': None,
                'error': None,
                'created_at': datetime.now().isoformat(),
                'finished_at': None
            }
        return task_id

    def update_task(self, task_id, **kwargs):
        """更新任务状态"""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)
                if kwargs.get('status') in ['completed', 'failed']:
                    self.tasks[task_id]['finished_at'] = datetime.now().isoformat()

    def get_task(self, task_id):
        """获取任务信息"""
        with self.lock:
            if task_id in self.tasks:
                return self.tasks[task_id].copy()
            return None

    def get_all_tasks(self):
        """获取所有任务"""
        with self.lock:
            return {k: v.copy() for k, v in self.tasks.items()}

    def submit_task(self, task_id, func, *args, **kwargs):
        """提交任务到线程池执行"""
        def wrapper():
            try:
                self.update_task(task_id, status='running', message='执行中', progress=10)
                result = func(task_id, *args, **kwargs)
                self.update_task(task_id, status='completed', progress=100, result=result)
            except Exception as e:
                self.update_task(task_id, status='failed', error=str(e))

        self.executor.submit(wrapper)

    def cleanup_old_tasks(self, max_age_hours=24):
        """清理旧任务"""
        cutoff = datetime.now().timestamp() - max_age_hours * 3600
        with self.lock:
            to_delete = []
            for task_id, task in self.tasks.items():
                if task.get('finished_at'):
                    finished = datetime.fromisoformat(task['finished_at']).timestamp()
                    if finished < cutoff:
                        to_delete.append(task_id)
            for task_id in to_delete:
                del self.tasks[task_id]

# 全局任务管理器
task_manager = TaskManager()

# 配置
BASE_DIR = Path(__file__).parent.parent
UPLOAD_FOLDER = BASE_DIR / 'uploads'
OUTPUT_FOLDER = BASE_DIR / 'outputs'
DATABASE_FILE = BASE_DIR / 'database.json'

# Kindle 配置
KINDLE_ARTICLE_PATH = Path("E:/documents/Downloads/Items01/article")

# 确保目录存在
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'md', 'markdown'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_database():
    """加载数据库"""
    if DATABASE_FILE.exists():
        with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'files': {}}

def save_database(db):
    """保存数据库"""
    with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_file_info(file_id):
    """获取文件信息"""
    db = load_database()
    if file_id not in db['files']:
        return None
    return db['files'][file_id]

def update_file_info(file_id, info):
    """更新文件信息"""
    db = load_database()
    db['files'][file_id] = info
    save_database(db)

def delete_file_from_db(file_id):
    """从数据库删除文件记录"""
    db = load_database()
    if file_id in db['files']:
        del db['files'][file_id]
        save_database(db)

def check_kindle_connected():
    """检查 Kindle 是否连接"""
    return KINDLE_ARTICLE_PATH.exists()

def get_kindle_files():
    """获取 Kindle 中已有的 KFX/EPUB 文件列表（不带扩展名）"""
    if not check_kindle_connected():
        return set()

    kindle_files = set()
    try:
        # 获取所有 .kfx 和 .epub 文件
        for ext in ['*.kfx', '*.epub']:
            for f in KINDLE_ARTICLE_PATH.glob(ext):
                kindle_files.add(f.stem)
        print(f"Kindle 中的文件：{kindle_files}")
    except Exception as e:
        print(f"获取 Kindle 文件列表失败：{e}")
    return kindle_files

def copy_to_kindle(file_id):
    """将 KFX 文件及相关 SDR 文件夹复制到 Kindle"""
    if not check_kindle_connected():
        return False, "Kindle 未连接"

    info = get_file_info(file_id)
    if not info:
        return False, "文件不存在"

    # 使用数据库记录的文件名（original_name 去掉扩展名）
    file_name = info.get('name', '')
    if not file_name:
        return False, "文件名无效"

    kfx_path = OUTPUT_FOLDER / f"{file_id}.kfx"
    epub_path = OUTPUT_FOLDER / f"{file_id}.epub"

    if not kfx_path.exists() and not epub_path.exists():
        return False, "KFX/EPUB 文件不存在"

    try:
        # 复制 KFX 文件（优先）或 EPUB 文件
        if kfx_path.exists():
            dest_kfx = KINDLE_ARTICLE_PATH / f"{file_name}.kfx"
            shutil.copy2(kfx_path, dest_kfx)
            print(f"Copied: {kfx_path} -> {dest_kfx}")
        else:
            dest_epub = KINDLE_ARTICLE_PATH / f"{file_name}.epub"
            shutil.copy2(epub_path, dest_epub)
            print(f"Copied: {epub_path} -> {dest_epub}")

        # 复制 SDR 文件夹（如果存在）
        sdr_path = OUTPUT_FOLDER / f"{file_id}.sdr"
        if sdr_path.exists() and sdr_path.is_dir():
            dest_sdr = KINDLE_ARTICLE_PATH / f"{file_name}.sdr"
            if dest_sdr.exists():
                shutil.rmtree(dest_sdr)
            shutil.copytree(sdr_path, dest_sdr)
            print(f"Copied SDR: {sdr_path} -> {dest_sdr}")

        return True, "推送成功"
    except Exception as e:
        print(f"Copy to Kindle failed: {e}")
        return False, f"复制失败：{str(e)}"

def delete_from_kindle(file_id):
    """从 Kindle 删除 KFX 文件及相关 SDR 文件夹"""
    if not check_kindle_connected():
        return False, "Kindle 未连接"

    info = get_file_info(file_id)
    if not info:
        return False, "文件不存在"

    file_name = info.get('name', '')
    if not file_name:
        return False, "文件名无效"

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

        # 删除以 file_name_ 开头的 SDR 文件夹（Kindle 生成的 {书名}_{唯一 ID}.sdr 格式）
        try:
            sdr_prefix = f"{file_name}_"
            for sdr_dir in KINDLE_ARTICLE_PATH.iterdir():
                if sdr_dir.is_dir() and sdr_dir.name.startswith(sdr_prefix) and sdr_dir.name.endswith('.sdr'):
                    shutil.rmtree(sdr_dir)
                    deleted_items.append(sdr_dir.name)
                    print(f"Deleted SDR (prefix match): {sdr_dir}")
        except Exception as e:
            print(f"Error scanning SDR folders: {e}")

        print(f"Deleted from Kindle: {deleted_items}")
        return True, f"删除成功，共删除 {len(deleted_items)} 个项目"
    except Exception as e:
        print(f"Delete from Kindle failed: {e}")
        return False, f"删除失败：{str(e)}"

def scan_existing_files():
    """扫描 database 目录中已有的文件并导入"""
    db = load_database()
    database_dir = BASE_DIR / 'database'

    if not database_dir.exists():
        return

    # 扫描所有 md 文件
    for md_file in database_dir.glob('*.md'):
        # 生成文件 ID (使用文件名的 hash)
        file_id = hashlib.md5(md_file.stem.encode()).hexdigest()[:8]

        # 检查是否已存在
        if file_id in db['files']:
            continue

        # 检查对应的 kfx 和 epub 文件
        kfx_file = database_dir / f"{md_file.stem}.kfx"
        epub_file = database_dir / f"{md_file.stem}.epub"

        # 复制文件到 uploads 和 outputs 目录
        upload_path = UPLOAD_FOLDER / f"{file_id}.md"
        shutil.copy2(md_file, upload_path)

        # 复制输出文件
        has_kfx = False
        has_epub = False
        if kfx_file.exists():
            output_path = OUTPUT_FOLDER / f"{file_id}.kfx"
            shutil.copy2(kfx_file, output_path)
            has_kfx = True
        if epub_file.exists():
            output_path = OUTPUT_FOLDER / f"{file_id}.epub"
            shutil.copy2(epub_file, output_path)
            has_epub = True

        # 记录到数据库
        stat = md_file.stat()
        db['files'][file_id] = {
            'name': md_file.stem,
            'original_name': md_file.name,
            'author': 'Kindle User',
            'upload_time': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'convert_time': datetime.fromtimestamp(stat.st_mtime).isoformat() if (has_kfx or has_epub) else '',
            'status': 'converted' if has_kfx else ('converted_epub' if has_epub else 'uploaded')
        }

    save_database(db)

# 启动时扫描现有文件
scan_existing_files()


@app.route('/')
def index():
    """主页"""
    db = load_database()
    kindle_files = get_kindle_files()  # 获取 Kindle 中的文件列表

    files = []
    for file_id, info in db['files'].items():
        # 检查文件是否存在
        md_path = UPLOAD_FOLDER / f"{file_id}.md"
        kfx_path = OUTPUT_FOLDER / f"{file_id}.kfx"
        epub_path = OUTPUT_FOLDER / f"{file_id}.epub"

        # 检查是否已导入 Kindle（通过文件名匹配）
        file_name = info.get('name', '')
        is_imported = file_name in kindle_files

        file_info = {
            'id': file_id,
            'name': info.get('name', 'Unknown'),
            'author': info.get('author', 'Unknown'),
            'upload_time': info.get('upload_time', ''),
            'convert_time': info.get('convert_time', ''),
            'status': info.get('status', 'pending'),
            'has_md': md_path.exists(),
            'has_kfx': kfx_path.exists(),
            'has_epub': epub_path.exists(),
            'is_imported': is_imported
        }
        files.append(file_info)

    # 按上传时间倒序排列
    files.sort(key=lambda x: x['upload_time'], reverse=True)
    return render_template('index.html', files=files)

@app.route('/upload', methods=['POST'])
def upload_file():
    """上传 Markdown 文件"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Only .md and .markdown files are allowed'}), 400

    # 生成唯一 ID
    file_id = str(uuid.uuid4())[:8]
    original_name = secure_filename(file.filename)
    display_name = Path(original_name).stem

    # 获取额外参数
    author = request.form.get('author', 'Kindle User')
    custom_name = request.form.get('name', display_name)

    # 保存文件
    md_path = UPLOAD_FOLDER / f"{file_id}.md"
    file.save(md_path)

    # 记录到数据库
    file_info = {
        'name': custom_name,
        'original_name': original_name,
        'author': author,
        'upload_time': datetime.now().isoformat(),
        'status': 'uploaded'
    }
    update_file_info(file_id, file_info)

    return jsonify({
        'success': True,
        'file_id': file_id,
        'name': custom_name
    })

@app.route('/convert/<file_id>', methods=['POST'])
def convert_file(file_id):
    """转换文件"""
    info = get_file_info(file_id)
    if not info:
        return jsonify({'error': 'File not found'}), 404

    md_path = UPLOAD_FOLDER / f"{file_id}.md"
    if not md_path.exists():
        return jsonify({'error': 'Source file not found'}), 404

    try:
        # 设置输出路径
        output_path = OUTPUT_FOLDER / f"{file_id}.kfx"

        # 执行转换
        converter = MarkdownToKFX(
            markdown_file=str(md_path),
            output_file=str(output_path),
            title=info.get('name', 'Untitled'),
            author=info.get('author', 'Unknown')
        )
        result = converter.convert()

        # 检查输出文件
        status = 'converted'
        if result.suffix == '.epub':
            # 如果是 epub，重命名
            epub_path = OUTPUT_FOLDER / f"{file_id}.epub"
            if result != epub_path:
                shutil.move(str(result), str(epub_path))
            status = 'converted_epub'

        # 更新数据库
        info['status'] = status
        info['convert_time'] = datetime.now().isoformat()
        update_file_info(file_id, info)

        return jsonify({
            'success': True,
            'status': status,
            'message': f'Converted to {result.suffix}'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<file_id>/<file_type>')
def download_file(file_id, file_type):
    """下载文件"""
    if file_type == 'md':
        file_path = UPLOAD_FOLDER / f"{file_id}.md"
    elif file_type == 'kfx':
        file_path = OUTPUT_FOLDER / f"{file_id}.kfx"
    elif file_type == 'epub':
        file_path = OUTPUT_FOLDER / f"{file_id}.epub"
    else:
        return jsonify({'error': 'Invalid file type'}), 400

    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404

    info = get_file_info(file_id)
    name = info.get('name', 'download') if info else 'download'

    return send_file(
        file_path,
        as_attachment=True,
        download_name=f"{name}{file_path.suffix}"
    )

@app.route('/rename/<file_id>', methods=['POST'])
def rename_file(file_id):
    """重命名文件"""
    info = get_file_info(file_id)
    if not info:
        return jsonify({'error': 'File not found'}), 404

    new_name = request.json.get('name', '').strip()
    if not new_name:
        return jsonify({'error': 'Name cannot be empty'}), 400

    info['name'] = new_name
    update_file_info(file_id, info)

    return jsonify({'success': True, 'name': new_name})

@app.route('/update_author/<file_id>', methods=['POST'])
def update_author(file_id):
    """更新作者"""
    info = get_file_info(file_id)
    if not info:
        return jsonify({'error': 'File not found'}), 404

    new_author = request.json.get('author', '').strip()
    if not new_author:
        return jsonify({'error': 'Author cannot be empty'}), 400

    info['author'] = new_author
    update_file_info(file_id, info)

    return jsonify({'success': True, 'author': new_author})

@app.route('/delete/<file_id>', methods=['POST'])
def delete_file(file_id):
    """删除文件"""
    # 删除实际文件
    md_path = UPLOAD_FOLDER / f"{file_id}.md"
    kfx_path = OUTPUT_FOLDER / f"{file_id}.kfx"
    epub_path = OUTPUT_FOLDER / f"{file_id}.epub"

    for path in [md_path, kfx_path, epub_path]:
        if path.exists():
            path.unlink()

    # 删除关联的图片文件（微信/知乎文章下载的图片）
    images_dir = UPLOAD_FOLDER / 'images'
    if images_dir.exists():
        for img_file in images_dir.glob(f"{file_id}_*"):
            img_file.unlink()

    # 从数据库删除
    delete_file_from_db(file_id)

    return jsonify({'success': True})

@app.route('/batch_delete', methods=['POST'])
def batch_delete():
    """批量删除"""
    file_ids = request.json.get('ids', [])
    deleted = []

    for file_id in file_ids:
        md_path = UPLOAD_FOLDER / f"{file_id}.md"
        kfx_path = OUTPUT_FOLDER / f"{file_id}.kfx"
        epub_path = OUTPUT_FOLDER / f"{file_id}.epub"

        for path in [md_path, kfx_path, epub_path]:
            if path.exists():
                path.unlink()

        delete_file_from_db(file_id)
        deleted.append(file_id)

    return jsonify({'success': True, 'deleted': deleted})

@app.route('/batch_convert', methods=['POST'])
def batch_convert():
    """批量转换（后台异步）"""
    file_ids = request.json.get('ids', [])

    if not file_ids:
        return jsonify({'error': 'No files selected'}), 400

    # 创建后台任务
    task_id = task_manager.create_task('batch_convert', {
        'file_ids': file_ids,
        'total': len(file_ids)
    })

    # 提交任务到线程池
    task_manager.submit_task(task_id, _do_batch_convert, file_ids)

    return jsonify({
        'success': True,
        'task_id': task_id,
        'message': f'已创建转换任务，共 {len(file_ids)} 个文件'
    })


def _do_batch_convert(task_id, file_ids):
    """执行批量转换（后台任务）"""
    results = []
    total = len(file_ids)

    for i, file_id in enumerate(file_ids):
        try:
            progress = int((i / total) * 90) + 5
            task_manager.update_task(task_id, progress=progress,
                                     message=f'正在转换 {i+1}/{total}...')

            info = get_file_info(file_id)
            if not info:
                results.append({'id': file_id, 'status': 'error', 'message': 'Not found'})
                continue

            md_path = UPLOAD_FOLDER / f"{file_id}.md"
            if not md_path.exists():
                results.append({'id': file_id, 'status': 'error', 'message': 'Source missing'})
                continue

            output_path = OUTPUT_FOLDER / f"{file_id}.kfx"
            converter = MarkdownToKFX(
                markdown_file=str(md_path),
                output_file=str(output_path),
                title=info.get('name', 'Untitled'),
                author=info.get('author', 'Unknown'),
                skip_mathml=True  # KFX 不支持复杂 MathML
            )
            result = converter.convert()

            status = 'converted'
            if result.suffix == '.epub':
                epub_path = OUTPUT_FOLDER / f"{file_id}.epub"
                if result != epub_path:
                    shutil.move(str(result), str(epub_path))
                status = 'converted_epub'

            info['status'] = status
            info['convert_time'] = datetime.now().isoformat()
            update_file_info(file_id, info)

            results.append({'id': file_id, 'status': 'success'})
        except Exception as e:
            results.append({'id': file_id, 'status': 'error', 'message': str(e)})

    success_count = sum(1 for r in results if r['status'] == 'success')
    task_manager.update_task(task_id, progress=100, message='转换完成',
                             result={'results': results, 'total': total, 'success_count': success_count})

    return {'results': results, 'total': total, 'success_count': success_count}

@app.route('/batch_push_kindle', methods=['POST'])
def batch_push_kindle():
    """批量推送到 Kindle"""
    if not check_kindle_connected():
        return jsonify({'success': False, 'error': 'Kindle 未连接'}), 400

    file_ids = request.json.get('ids', [])
    results = []

    for file_id in file_ids:
        try:
            success, message = copy_to_kindle(file_id)
            if success:
                results.append({'id': file_id, 'status': 'success', 'message': message})
            else:
                results.append({'id': file_id, 'status': 'error', 'message': message})
        except Exception as e:
            results.append({'id': file_id, 'status': 'error', 'message': str(e)})

    success_count = sum(1 for r in results if r['status'] == 'success')
    return jsonify({
        'success': True,
        'results': results,
        'total': len(file_ids),
        'success_count': success_count
    })

@app.route('/batch_delete_kindle', methods=['POST'])
def batch_delete_kindle():
    """批量从 Kindle 删除"""
    if not check_kindle_connected():
        return jsonify({'success': False, 'error': 'Kindle 未连接'}), 400

    file_ids = request.json.get('ids', [])
    results = []

    for file_id in file_ids:
        try:
            success, message = delete_from_kindle(file_id)
            if success:
                results.append({'id': file_id, 'status': 'success', 'message': message})
            else:
                results.append({'id': file_id, 'status': 'error', 'message': message})
        except Exception as e:
            results.append({'id': file_id, 'status': 'error', 'message': str(e)})

    success_count = sum(1 for r in results if r['status'] == 'success')
    return jsonify({
        'success': True,
        'results': results,
        'total': len(file_ids),
        'success_count': success_count
    })

@app.route('/file_info/<file_id>')
def file_info(file_id):
    """获取文件详情"""
    info = get_file_info(file_id)
    if not info:
        return jsonify({'error': 'File not found'}), 404

    md_path = UPLOAD_FOLDER / f"{file_id}.md"
    kfx_path = OUTPUT_FOLDER / f"{file_id}.kfx"
    epub_path = OUTPUT_FOLDER / f"{file_id}.epub"

    return jsonify({
        'id': file_id,
        'name': info.get('name', 'Unknown'),
        'original_name': info.get('original_name', ''),
        'author': info.get('author', 'Unknown'),
        'upload_time': info.get('upload_time', ''),
        'convert_time': info.get('convert_time', ''),
        'status': info.get('status', 'pending'),
        'has_md': md_path.exists(),
        'has_kfx': kfx_path.exists(),
        'has_epub': epub_path.exists(),
        'md_size': md_path.stat().st_size if md_path.exists() else 0,
        'kfx_size': kfx_path.stat().st_size if kfx_path.exists() else 0,
        'epub_size': epub_path.stat().st_size if epub_path.exists() else 0
    })

@app.route('/preview/<file_id>')
def preview_file(file_id):
    """预览 Markdown 内容"""
    md_path = UPLOAD_FOLDER / f"{file_id}.md"
    if not md_path.exists():
        return jsonify({'error': 'File not found'}), 404

    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    return jsonify({'content': content})

@app.route('/kindle/status')
def kindle_status():
    """检查 Kindle 连接状态"""
    is_connected = check_kindle_connected()
    return jsonify({
        'connected': is_connected,
        'path': str(KINDLE_ARTICLE_PATH) if is_connected else None
    })

@app.route('/kindle/push/<file_id>', methods=['POST'])
def push_to_kindle(file_id):
    """推送文件到 Kindle"""
    # 调试信息
    info = get_file_info(file_id)
    print(f"Push to Kindle - file_id: {file_id}, name: {info.get('name') if info else 'N/A'}")

    success, message = copy_to_kindle(file_id)
    if success:
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'message': message}), 400

@app.route('/kindle/delete/<file_id>', methods=['POST'])
def delete_from_kindle_api(file_id):
    """从 Kindle 删除文件"""
    success, message = delete_from_kindle(file_id)
    if success:
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'message': message}), 400

@app.route('/kindle/refresh', methods=['POST'])
def refresh_kindle_status():
    """刷新 Kindle 状态（用于前端轮询后手动刷新）"""
    return jsonify({'success': True})


# ==================== 知乎下载 API ====================

ZHIHU_COOKIE_FILE = BASE_DIR / 'config' / 'zhihu_cookies.json'
WECHAT_COOKIE_FILE = BASE_DIR / 'config' / 'wechat_cookies.json'

@app.route('/zhihu/status')
def zhihu_status():
    """检查知乎登录状态"""
    if not ZHIHU_AVAILABLE:
        return jsonify({
            'available': False,
            'error': 'Zhihu downloader not installed'
        })

    try:
        auth = ZhihuAuth(cookie_file=str(ZHIHU_COOKIE_FILE))
        cookies = auth.load_cookies()

        if not cookies:
            return jsonify({
                'available': True,
                'logged_in': False,
                'message': '未登录，请先登录知乎'
            })

        # 检查 Cookie 是否有效
        is_valid = auth.check_login_status()

        return jsonify({
            'available': True,
            'logged_in': is_valid,
            'message': '已登录' if is_valid else 'Cookie 已过期，请重新登录'
        })
    except Exception as e:
        return jsonify({
            'available': True,
            'logged_in': False,
            'error': str(e)
        })


@app.route('/zhihu/preview', methods=['POST'])
def zhihu_preview():
    """预览知乎文章信息（不下载）"""
    if not ZHIHU_AVAILABLE:
        return jsonify({'error': 'Zhihu downloader not available'}), 400

    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL 不能为空'}), 400

    # 验证 URL
    if 'zhihu.com' not in url:
        return jsonify({'error': '请输入有效的知乎链接'}), 400

    try:
        # 加载 cookies
        cookies = None
        has_cookies = False
        if ZHIHU_COOKIE_FILE.exists():
            auth = ZhihuAuth(cookie_file=str(ZHIHU_COOKIE_FILE))
            cookies = auth.load_cookies()
            has_cookies = bool(cookies)

        client = ZhihuClient(cookies=cookies)
        article_id = client.extract_article_id(url)

        if not article_id:
            return jsonify({'error': '无法解析知乎链接，请检查 URL 格式'}), 400

        # 获取文章信息
        if article_id.startswith('answer_'):
            answer_id = article_id.replace('answer_', '')
            api_url = f"https://www.zhihu.com/api/v4/answers/{answer_id}"
            params = {'include': 'content,author,question'}
            resp = client.session.get(api_url, params=params, timeout=15)
        else:
            api_url = f"https://www.zhihu.com/api/v4/articles/{article_id}"
            resp = client.session.get(api_url, timeout=15)

        if resp.status_code == 401:
            return jsonify({
                'error': '登录已过期，请重新登录知乎账号',
                'need_login': True
            }), 401

        if resp.status_code == 404:
            return jsonify({'error': '文章不存在或已删除'}), 404

        if resp.status_code == 403:
            return jsonify({'error': '访问被拒绝，请尝试使用浏览器模式'}), 403

        resp.raise_for_status()
        data = resp.json()

        # 提取关键信息
        title = data.get('title', 'Untitled')
        author = data.get('author', {}).get('name', 'Unknown')
        content = data.get('content') or data.get('html', '')
        excerpt = content[:300] if content else ''

        # 清理 HTML 标签获取纯文本摘要

        soup = BeautifulSoup(excerpt, 'html.parser')
        text_excerpt = soup.get_text()[:200]

        return jsonify({
            'success': True,
            'article_id': article_id,
            'title': title,
            'author': author,
            'excerpt': text_excerpt + '...',
            'url': url
        })

    except requests.RequestException as e:
        return jsonify({'error': f'网络请求失败: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'预览失败: {str(e)}'}), 500


@app.route('/zhihu/download', methods=['POST'])
def zhihu_download():
    """下载知乎文章并添加到文件列表（后台异步）"""
    if not ZHIHU_AVAILABLE:
        return jsonify({'error': 'Zhihu downloader not available'}), 400

    url = request.json.get('url', '').strip()
    custom_title = request.json.get('title') or ''
    custom_author = request.json.get('author') or ''

    if not url:
        return jsonify({'error': 'URL 不能为空'}), 400

    # 创建后台任务
    task_id = task_manager.create_task('zhihu_download', {
        'url': url,
        'title': custom_title,
        'author': custom_author
    })

    # 提交任务到线程池
    task_manager.submit_task(task_id, _do_zhihu_download, url, custom_title, custom_author)

    return jsonify({
        'success': True,
        'task_id': task_id,
        'message': '任务已创建，正在后台执行'
    })


def _do_zhihu_download(task_id, url, custom_title, custom_author):
    """执行知乎文章下载（后台任务）- 下载并转换"""
    try:
        task_manager.update_task(task_id, progress=5, message='正在加载 Cookie...')

        # 加载 cookies
        cookies = None
        if ZHIHU_COOKIE_FILE.exists():
            auth = ZhihuAuth(cookie_file=str(ZHIHU_COOKIE_FILE))
            cookies = auth.load_cookies()

        task_manager.update_task(task_id, progress=10, message='正在下载文章...')

        # 创建转换器
        converter = ZhihuToMarkdown(
            output_dir=str(BASE_DIR),
            cookies=cookies
        )

        # 尝试转换文章
        result = converter.convert(url, use_browser=False)

        # 如果 API 模式失败，尝试浏览器模式
        if not result:
            if not cookies:
                raise Exception('请先登录知乎账号')
            task_manager.update_task(task_id, progress=15, message='尝试浏览器模式...')
            result = converter.convert(url, use_browser=True)

        if not result:
            raise Exception('下载失败，可能是登录已过期或文章不存在')

        markdown_content, output_file = result

        # 读取下载的文件
        downloaded_path = Path(output_file)
        if not downloaded_path.exists():
            raise Exception('文件保存失败')

        task_manager.update_task(task_id, progress=40, message='正在保存文件...')

        # 生成文件 ID
        file_id = str(uuid.uuid4())[:8]

        # 确定标题和作者
        title = custom_title or downloaded_path.stem
        author = custom_author or 'Unknown'

        # 移动文件到 uploads 目录
        md_path = UPLOAD_FOLDER / f"{file_id}.md"
        shutil.move(str(downloaded_path), str(md_path))

        # 记录到数据库
        file_info = {
            'name': title,
            'original_name': f"{title}.md",
            'author': author,
            'upload_time': datetime.now().isoformat(),
            'status': 'uploaded',
            'source': 'zhihu',
            'source_url': url
        }
        update_file_info(file_id, file_info)

        # 执行转换
        task_manager.update_task(task_id, progress=60, message='正在转换为 KFX...')
        try:
            output_path = OUTPUT_FOLDER / f"{file_id}.kfx"
            kfx_converter = MarkdownToKFX(
                markdown_file=str(md_path),
                output_file=str(output_path),
                title=title,
                author=author
            )
            convert_result = kfx_converter.convert()

            status = 'converted'
            if convert_result.suffix == '.epub':
                epub_path = OUTPUT_FOLDER / f"{file_id}.epub"
                if convert_result != epub_path:
                    shutil.move(str(convert_result), str(epub_path))
                status = 'converted_epub'

            file_info['status'] = status
            file_info['convert_time'] = datetime.now().isoformat()
            update_file_info(file_id, file_info)

        except Exception as e:
            task_manager.update_task(task_id, progress=100, message=f'下载完成，转换失败: {str(e)}', result={
                'file_id': file_id,
                'name': title,
                'author': author,
                'convert_error': str(e)
            })
            return {'file_id': file_id, 'name': title, 'author': author, 'convert_error': str(e)}

        task_manager.update_task(task_id, progress=100, message='下载并转换完成', result={
            'file_id': file_id,
            'name': title,
            'author': author,
            'status': status
        })

        return {'file_id': file_id, 'name': title, 'author': author, 'status': status}

    except Exception as e:
        error_msg = str(e)
        task_manager.update_task(task_id, status='failed', error=error_msg)
        raise


# ==================== 微信下载 API ====================

@app.route('/wechat/status')
def wechat_status():
    """检查微信登录状态"""
    if not WECHAT_AVAILABLE:
        return jsonify({
            'available': False,
            'error': 'WeChat downloader not installed'
        })

    try:
        auth = WeChatAuth(cookie_file=str(WECHAT_COOKIE_FILE))
        cookies = auth.load_cookies()

        if not cookies:
            return jsonify({
                'available': True,
                'logged_in': False,
                'message': '未登录，请先登录微信公众号'
            })

        # 检查 Cookie 是否有效
        is_valid = auth.check_login_status()

        return jsonify({
            'available': True,
            'logged_in': is_valid,
            'message': '已登录' if is_valid else 'Cookie 已过期，请重新登录'
        })
    except Exception as e:
        return jsonify({
            'available': True,
            'logged_in': False,
            'error': str(e)
        })


@app.route('/wechat/preview', methods=['POST'])
def wechat_preview():
    """预览微信文章信息（不下载）"""
    if not WECHAT_AVAILABLE:
        return jsonify({'error': 'WeChat downloader not available'}), 400

    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL 不能为空'}), 400

    # 验证 URL
    if 'weixin.qq.com' not in url and 'mp.weixin.qq.com' not in url:
        return jsonify({'error': '请输入有效的微信公众号文章链接'}), 400

    try:
        # 加载 cookies
        cookies = None
        has_cookies = False
        if WECHAT_COOKIE_FILE.exists():
            auth = WeChatAuth(cookie_file=str(WECHAT_COOKIE_FILE))
            cookies = auth.load_cookies()
            has_cookies = bool(cookies)

        client = WeChatClient(cookies=cookies)
        article_id = client.extract_article_id(url)

        if not article_id:
            return jsonify({'error': '无法解析微信链接，请检查 URL 格式'}), 400

        # 使用浏览器模式获取文章信息
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
            )

            # 注入 cookies
            if cookies:
                cookies_list = []
                for name, value in cookies.items():
                    cookies_list.append({
                        'name': name,
                        'value': value,
                        'domain': '.qq.com',
                        'path': '/'
                    })
                if cookies_list:
                    context.add_cookies(cookies_list)

            page = context.new_page()
            page.goto(url, wait_until='networkidle', timeout=60000)

            # 等待内容加载
            try:
                page.wait_for_selector('#activity-name, .rich_media_title', timeout=15000)
            except:
                pass

            # 获取页面内容
            html = page.content()
            browser.close()

            soup = BeautifulSoup(html, 'html.parser')

            # 获取标题
            title_tag = soup.find('h1', id='activity-name') or soup.find('h1', class_='rich_media_title')
            if not title_tag:
                title_tag = soup.select_one('meta[name="description"]') or soup.select_one('title')
            title = title_tag.get('content', '').strip() if title_tag and title_tag.name == 'meta' else (title_tag.get_text().strip() if title_tag else 'Untitled')

            # 获取作者
            author_tag = soup.find('div', class_='rich_media_meta_nickname')
            if not author_tag:
                author_tag = soup.find('meta', attrs={'name': 'author'})
            author = author_tag.get_text().strip() if author_tag else 'Unknown'

            # 获取摘要
            content_div = soup.find('div', id='js_content') or soup.find('div', class_='rich_media_content')
            excerpt = content_div.get_text()[:300] if content_div else ''

            return jsonify({
                'success': True,
                'article_id': article_id,
                'title': title,
                'author': author,
                'excerpt': excerpt[:200] + '...' if excerpt else '',
                'url': url
            })

    except Exception as e:
        error_msg = str(e)
        if 'playwright' in error_msg.lower():
            return jsonify({'error': '需要安装 playwright: pip install playwright && playwright install chromium'}), 500
        return jsonify({'error': f'预览失败：{error_msg}'}), 500


@app.route('/wechat/download', methods=['POST'])
def wechat_download():
    """下载微信文章并添加到文件列表（后台异步）"""
    if not WECHAT_AVAILABLE:
        return jsonify({'error': 'WeChat downloader not available'}), 400

    url = request.json.get('url', '').strip()
    custom_title = request.json.get('title') or ''
    custom_author = request.json.get('author') or ''

    if not url:
        return jsonify({'error': 'URL 不能为空'}), 400

    # 创建后台任务
    task_id = task_manager.create_task('wechat_download', {
        'url': url,
        'title': custom_title,
        'author': custom_author
    })

    # 提交任务到线程池
    task_manager.submit_task(task_id, _do_wechat_download, url, custom_title, custom_author)

    return jsonify({
        'success': True,
        'task_id': task_id,
        'message': '任务已创建，正在后台执行'
    })


def _do_wechat_download(task_id, url, custom_title, custom_author):
    """执行微信文章下载（后台任务）- 下载并转换"""
    try:
        task_manager.update_task(task_id, progress=5, message='正在加载 Cookie...')

        # 加载 cookies
        cookies = None
        if WECHAT_COOKIE_FILE.exists():
            auth = WeChatAuth(cookie_file=str(WECHAT_COOKIE_FILE))
            cookies = auth.load_cookies()

        task_manager.update_task(task_id, progress=10, message='正在下载文章...')

        # 生成文件 ID（提前生成，用于建立独立的 images 目录）
        file_id = str(uuid.uuid4())[:8]

        # 创建转换器，直接输出到 uploads 目录
        converter = WeChatToMarkdown(
            output_dir=str(UPLOAD_FOLDER),
            cookies=cookies,
            file_prefix=file_id  # 使用 file_id 作为文件前缀
        )

        # 执行转换（微信默认使用浏览器模式）
        result = converter.convert(url, use_browser=True)

        if not result:
            raise Exception('下载失败，可能是登录已过期或文章不存在')

        markdown_content, output_file = result

        # 读取下载的文件
        downloaded_path = Path(output_file)
        if not downloaded_path.exists():
            raise Exception('文件保存失败')

        task_manager.update_task(task_id, progress=40, message='正在保存文件...')

        # 从 markdown YAML front matter 中提取标题
        extracted_title = file_id  # 默认使用 file_id
        if markdown_content.startswith('---'):
            import re
            title_match = re.search(r'^title:\s*(.+)$', markdown_content, re.MULTILINE)
            if title_match:
                extracted_title = title_match.group(1).strip()

        # 确定标题和作者
        title = custom_title or extracted_title
        author = custom_author or 'Unknown'

        # 重命名文件为 file_id.md（如果还不是）
        md_path = UPLOAD_FOLDER / f"{file_id}.md"
        if downloaded_path != md_path:
            shutil.move(str(downloaded_path), str(md_path))

        # 记录到数据库
        file_info = {
            'name': title,
            'original_name': f"{title}.md",
            'author': author,
            'upload_time': datetime.now().isoformat(),
            'status': 'uploaded',
            'source': 'wechat',
            'source_url': url
        }
        update_file_info(file_id, file_info)

        # 执行转换
        task_manager.update_task(task_id, progress=60, message='正在转换为 KFX...')
        try:
            output_path = OUTPUT_FOLDER / f"{file_id}.kfx"
            kfx_converter = MarkdownToKFX(
                markdown_file=str(md_path),
                output_file=str(output_path),
                title=title,
                author=author
            )
            convert_result = kfx_converter.convert()

            status = 'converted'
            if convert_result.suffix == '.epub':
                epub_path = OUTPUT_FOLDER / f"{file_id}.epub"
                if convert_result != epub_path:
                    shutil.move(str(convert_result), str(epub_path))
                status = 'converted_epub'

            file_info['status'] = status
            file_info['convert_time'] = datetime.now().isoformat()
            update_file_info(file_id, file_info)

        except Exception as e:
            task_manager.update_task(task_id, progress=100, message=f'下载完成，转换失败: {str(e)}', result={
                'file_id': file_id,
                'name': title,
                'author': author,
                'convert_error': str(e)
            })
            return {'file_id': file_id, 'name': title, 'author': author, 'convert_error': str(e)}

        task_manager.update_task(task_id, progress=100, message='下载并转换完成', result={
            'file_id': file_id,
            'name': title,
            'author': author,
            'status': status
        })

        return {'file_id': file_id, 'name': title, 'author': author, 'status': status}

    except Exception as e:
        error_msg = str(e)
        task_manager.update_task(task_id, status='failed', error=error_msg)
        raise


if __name__ == '__main__':
    print("=" * 50)
    print("Markdown to KFX Converter WebUI")
    print("=" * 50)
    print(f"Upload folder: {UPLOAD_FOLDER}")
    print(f"Output folder: {OUTPUT_FOLDER}")
    print(f"Database: {DATABASE_FILE}")
    print(f"Kindle path: {KINDLE_ARTICLE_PATH}")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)


# ==================== 后台任务 API ====================

@app.route('/task/status/<task_id>')
def get_task_status(task_id):
    """获取任务状态"""
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


@app.route('/task/list')
def get_task_list():
    """获取所有任务列表"""
    return jsonify(task_manager.get_all_tasks())