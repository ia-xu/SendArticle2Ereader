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
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from werkzeug.utils import secure_filename

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from md2markdown_v5 import MarkdownToKFX

app = Flask(__name__)

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
    """批量转换"""
    file_ids = request.json.get('ids', [])
    results = []

    for file_id in file_ids:
        info = get_file_info(file_id)
        if not info:
            results.append({'id': file_id, 'status': 'error', 'message': 'Not found'})
            continue

        md_path = UPLOAD_FOLDER / f"{file_id}.md"
        if not md_path.exists():
            results.append({'id': file_id, 'status': 'error', 'message': 'Source missing'})
            continue

        try:
            output_path = OUTPUT_FOLDER / f"{file_id}.kfx"
            converter = MarkdownToKFX(
                markdown_file=str(md_path),
                output_file=str(output_path),
                title=info.get('name', 'Untitled'),
                author=info.get('author', 'Unknown')
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

    return jsonify({'success': True, 'results': results})

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