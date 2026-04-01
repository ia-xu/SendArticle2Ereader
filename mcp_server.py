"""
MCP Server for tokindle - Markdown to Kindle KFX Converter

使用 FastMCP 简化实现。

Claude Desktop 配置示例 (claude_desktop_config.json):
{
  "mcpServers": {
    "tokindle": {
      "command": "literal:/path/to/your/python",
      "args": ["literal:/path/to/tokindle/mcp_server.py"],
      "env": {}
    }
  }
}
"""
import os
import sys
import json
import uuid
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Literal, Optional

# 设置 MCP 模式环境变量，避免 md2kfx 重定向 stdout
os.environ['TOKINDLE_MCP_MODE'] = '1'

# 确保项目路径在 sys.path 中
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
sys.path.insert(0, str(PROJECT_ROOT / 'src' / 'downloader'))

from mcp.server.fastmcp import FastMCP

# 导入配置和工具
from src.config import (
    BASE_DIR, UPLOAD_FOLDER, OUTPUT_FOLDER,
    ZHIHU_COOKIE_FILE, WECHAT_COOKIE_FILE, KINDLE_ARTICLE_PATH,
    load_user_config
)
from src.md2kfx import MarkdownToKFX
from src.tools.database import update_file_info
from src.tools.kindle import (
    check_kindle_connected,
    get_kindle_files,
    copy_to_kindle,
    delete_from_kindle as _delete_from_kindle_impl
)
from src.tools.file_manager import (
    list_all_files,
    get_file_detail,
    delete_file_complete,
    search_files_by_keyword
)

# 下载器导入
try:
    from zhihu2markdown import ZhihuAuth, ZhihuToMarkdown
    ZHIHU_AVAILABLE = True
except ImportError:
    ZHIHU_AVAILABLE = False

try:
    from wechat2markdown import WeChatAuth, WeChatToMarkdown
    WECHAT_AVAILABLE = True
except ImportError:
    WECHAT_AVAILABLE = False

try:
    from arxiv2markdown import ArxivToMarkdown
    ARXIV_AVAILABLE = True
except ImportError:
    ARXIV_AVAILABLE = False


# 创建 FastMCP 实例
mcp = FastMCP("tokindle",
              host="127.0.0.1", port=48000
              )


# ============ 辅助函数 ============

def detect_url_type(url: str) -> str:
    """识别 URL 类型"""
    url_lower = url.lower()
    if 'zhihu.com' in url_lower:
        return 'zhihu'
    elif 'mp.weixin.qq.com' in url_lower or 'weixin.qq.com' in url_lower:
        return 'wechat'
    elif 'arxiv.org' in url_lower:
        return 'arxiv'
    return 'unknown'


def _convert_to_kfx(file_id: str, md_path: Path, title: str, author: str) -> dict:
    """转换 Markdown 为 KFX/EPUB"""
    result = {
        'status': 'uploaded',
        'has_kfx': False,
        'has_epub': False
    }

    try:
        output_path = OUTPUT_FOLDER / f"{file_id}.kfx"
        epub_output_path = OUTPUT_FOLDER / f"{file_id}.epub"

        kfx_converter = MarkdownToKFX(
            markdown_file=str(md_path),
            output_file=str(output_path),
            title=title,
            author=author
        )
        convert_result = kfx_converter.convert()

        # 同时保存 epub 文件
        user_config = load_user_config()
        enable_epub = user_config.get('enable_epub_support', True)
        if enable_epub and hasattr(kfx_converter, 'epub_file') and kfx_converter.epub_file and kfx_converter.epub_file.exists():
            shutil.copy2(str(kfx_converter.epub_file), str(epub_output_path))

        result['status'] = 'converted'
        result['has_kfx'] = output_path.exists()
        result['has_epub'] = epub_output_path.exists()

        if convert_result.suffix == '.epub':
            if convert_result != epub_output_path:
                shutil.move(str(convert_result), str(epub_output_path))
            result['status'] = 'converted_epub'

        result['convert_time'] = datetime.now().isoformat()

    except Exception as e:
        result['convert_error'] = str(e)

    return result


def _upload_local_file_sync(file_path: str, custom_title: str = None, custom_author: str = None) -> dict:
    """上传本地 Markdown 文件（同步）"""
    try:
        src_path = Path(file_path)
        if not src_path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

        if src_path.suffix.lower() not in ['.md', '.markdown']:
            return {"success": False, "error": "只支持 Markdown 文件 (.md 或 .markdown)"}

        file_id = str(uuid.uuid4())[:8]

        # 从文件名或内容提取标题
        content = src_path.read_text(encoding='utf-8')

        # 尝试从 YAML frontmatter 提取标题和作者
        import re
        extracted_title = src_path.stem
        extracted_author = 'Unknown'

        if content.startswith('---'):
            frontmatter_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
            if frontmatter_match:
                frontmatter = frontmatter_match.group(1)
                title_match = re.search(r'^title:\s*(.+)$', frontmatter, re.MULTILINE)
                if title_match:
                    extracted_title = title_match.group(1).strip().strip('"\'')
                author_match = re.search(r'^author:\s*(.+)$', frontmatter, re.MULTILINE)
                if author_match:
                    extracted_author = author_match.group(1).strip().strip('"\'')

        # 或者从第一个 # 标题提取
        if extracted_title == src_path.stem:
            first_title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if first_title_match:
                extracted_title = first_title_match.group(1).strip()

        title = custom_title or extracted_title
        author = custom_author or extracted_author

        # 复制文件到 uploads 目录
        md_path = UPLOAD_FOLDER / f"{file_id}.md"
        shutil.copy2(str(src_path), str(md_path))

        # 复制关联的 images 目录（如果存在）
        src_images_dir = src_path.parent / 'images'
        if src_images_dir.exists() and src_images_dir.is_dir():
            dest_images_dir = UPLOAD_FOLDER / f"{file_id}_images"
            if dest_images_dir.exists():
                shutil.rmtree(dest_images_dir)
            shutil.copytree(src_images_dir, dest_images_dir)

        # 更新数据库
        file_info = {
            'name': title,
            'original_name': src_path.name,
            'author': author,
            'upload_time': datetime.now().isoformat(),
            'status': 'uploaded',
            'source': 'upload',
            'source_url': str(src_path.absolute())
        }
        update_file_info(file_id, file_info)

        # 转换为 KFX/EPUB
        convert_result = _convert_to_kfx(file_id, md_path, title, author)
        file_info.update(convert_result)
        update_file_info(file_id, file_info)

        return {
            "success": True,
            "file_id": file_id,
            "title": title,
            "author": author,
            "source": "upload",
            "original_path": str(src_path.absolute()),
            "has_kfx": convert_result.get('has_kfx', False),
            "has_epub": convert_result.get('has_epub', False),
            "status": convert_result.get('status', 'uploaded'),
            "message": "上传并转换成功"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def _upload_local_files_sync(file_paths: list[str], titles: list[str] = None, authors: list[str] = None) -> dict:
    """批量上传本地 Markdown 文件（同步）"""
    if not file_paths:
        return {"success": False, "error": "文件路径列表不能为空"}

    results = []
    success_count = 0
    failed_count = 0

    for i, file_path in enumerate(file_paths):
        title = titles[i] if titles and i < len(titles) else None
        author = authors[i] if authors and i < len(authors) else None
        result = _upload_local_file_sync(file_path, title, author)
        results.append(result)
        if result.get("success"):
            success_count += 1
        else:
            failed_count += 1

    return {
        "success": True,
        "total": len(file_paths),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
        "message": f"完成 {success_count}/{len(file_paths)} 个文件上传转换"
    }


def _download_zhihu_sync(url: str, custom_title: str = None, custom_author: str = None) -> dict:
    """知乎下载（同步）"""
    if not ZHIHU_AVAILABLE:
        return {"success": False, "error": "知乎下载器不可用"}

    try:
        cookies = None
        if ZHIHU_COOKIE_FILE.exists():
            auth = ZhihuAuth(cookie_file=str(ZHIHU_COOKIE_FILE))
            cookies = auth.load_cookies()

        file_id = str(uuid.uuid4())[:8]

        converter = ZhihuToMarkdown(
            output_dir=str(UPLOAD_FOLDER),
            cookies=cookies,
            file_prefix=file_id
        )

        result = converter.convert(url, use_browser=False)

        if not result:
            if not cookies:
                return {"success": False, "error": "请先登录知乎账号"}
            result = converter.convert(url, use_browser=True)

        if not result:
            return {"success": False, "error": "下载失败，可能是登录已过期或文章不存在"}

        markdown_content, output_file = result
        downloaded_path = Path(output_file)
        if not downloaded_path.exists():
            return {"success": False, "error": "文件保存失败"}

        title = custom_title or file_id
        author = custom_author or 'Unknown'

        # 从 markdown 内容提取标题
        if markdown_content.startswith('---'):
            import re
            title_match = re.search(r'^title:\s*(.+)$', markdown_content, re.MULTILINE)
            if title_match:
                title = custom_title or title_match.group(1).strip()
            author_match = re.search(r'^author:\s*(.+)$', markdown_content, re.MULTILINE)
            if author_match and not custom_author:
                author = author_match.group(1).strip()

        md_path = UPLOAD_FOLDER / f"{file_id}.md"

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

        convert_result = _convert_to_kfx(file_id, md_path, title, author)
        file_info.update(convert_result)
        update_file_info(file_id, file_info)

        return {
            "success": True,
            "file_id": file_id,
            "title": title,
            "author": author,
            "source": "zhihu",
            "has_kfx": convert_result.get('has_kfx', False),
            "has_epub": convert_result.get('has_epub', False),
            "status": convert_result.get('status', 'uploaded'),
            "message": "下载并转换成功"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def _download_wechat_sync(url: str, custom_title: str = None, custom_author: str = None) -> dict:
    """微信下载（同步）"""
    if not WECHAT_AVAILABLE:
        return {"success": False, "error": "微信下载器不可用"}

    try:
        cookies = None
        if WECHAT_COOKIE_FILE.exists():
            auth = WeChatAuth(cookie_file=str(WECHAT_COOKIE_FILE))
            cookies = auth.load_cookies()

        file_id = str(uuid.uuid4())[:8]

        converter = WeChatToMarkdown(
            output_dir=str(UPLOAD_FOLDER),
            cookies=cookies,
            file_prefix=file_id
        )

        result = converter.convert(url, use_browser=True)

        if not result:
            return {"success": False, "error": "下载失败，可能是登录已过期或文章不存在"}

        markdown_content, output_file = result
        downloaded_path = Path(output_file)
        if not downloaded_path.exists():
            return {"success": False, "error": "文件保存失败"}

        import re
        extracted_title = file_id
        if markdown_content.startswith('---'):
            title_match = re.search(r'^title:\s*(.+)$', markdown_content, re.MULTILINE)
            if title_match:
                extracted_title = title_match.group(1).strip()

        title = custom_title or extracted_title
        author = custom_author or 'Unknown'

        md_path = UPLOAD_FOLDER / f"{file_id}.md"
        if downloaded_path != md_path:
            shutil.move(str(downloaded_path), str(md_path))

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

        convert_result = _convert_to_kfx(file_id, md_path, title, author)
        file_info.update(convert_result)
        update_file_info(file_id, file_info)

        return {
            "success": True,
            "file_id": file_id,
            "title": title,
            "author": author,
            "source": "wechat",
            "has_kfx": convert_result.get('has_kfx', False),
            "has_epub": convert_result.get('has_epub', False),
            "status": convert_result.get('status', 'uploaded'),
            "message": "下载并转换成功"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def _download_arxiv_sync(url: str, custom_title: str = None, custom_author: str = None) -> dict:
    """arXiv 下载（同步）"""
    if not ARXIV_AVAILABLE:
        return {"success": False, "error": "arXiv 下载器不可用"}

    try:
        import re

        file_id = str(uuid.uuid4())[:8]
        converter = ArxivToMarkdown(output_dir=str(UPLOAD_FOLDER))

        success, markdown_content, output_file = converter.convert(
            url=url,
            custom_title=custom_title,
            custom_author=custom_author
        )

        if not success or not output_file:
            return {"success": False, "error": "下载失败，请检查链接是否正确"}

        downloaded_path = Path(output_file)
        if not downloaded_path.exists():
            return {"success": False, "error": "文件保存失败"}

        markdown_content = downloaded_path.read_text(encoding='utf-8')
        title_match = re.search(r'^#\s+(.+)$', markdown_content, re.MULTILINE)
        extracted_title = title_match.group(1).strip() if title_match else file_id

        title = custom_title or extracted_title
        author = custom_author or 'Unknown'

        if not custom_author:
            author_match = re.search(r'\*\*Authors:\*\*\s*(.+?)(?:\n|$)', markdown_content)
            if author_match:
                author = author_match.group(1).strip()

        md_path = UPLOAD_FOLDER / f"{file_id}.md"
        if downloaded_path != md_path:
            shutil.move(str(downloaded_path), str(md_path))

        file_info = {
            'name': title,
            'original_name': f"{title}.md",
            'author': author,
            'upload_time': datetime.now().isoformat(),
            'status': 'uploaded',
            'source': 'arxiv',
            'source_url': url
        }
        update_file_info(file_id, file_info)

        convert_result = _convert_to_kfx(file_id, md_path, title, author)
        file_info.update(convert_result)
        update_file_info(file_id, file_info)

        return {
            "success": True,
            "file_id": file_id,
            "title": title,
            "author": author,
            "source": "arxiv",
            "has_kfx": convert_result.get('has_kfx', False),
            "has_epub": convert_result.get('has_epub', False),
            "status": convert_result.get('status', 'uploaded'),
            "message": "下载并转换成功"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============ MCP Tools ============

@mcp.tool()
def check_kindle_connection() -> dict:
    """检查墨水屏阅读器(Kindle)是否已连接到电脑"""
    connected = check_kindle_connected()
    return {
        "connected": connected,
        "device_path": str(KINDLE_ARTICLE_PATH) if connected else None,
        "message": "墨水屏阅读器已连接" if connected else "墨水屏阅读器未连接"
    }


async def _download_single_async(url: str, title: Optional[str] = None, author: Optional[str] = None) -> dict:
    """异步包装单个下载任务"""
    loop = asyncio.get_event_loop()
    url_type = detect_url_type(url)

    if url_type == 'zhihu':
        return await loop.run_in_executor(None, _download_zhihu_sync, url, title, author)
    elif url_type == 'wechat':
        return await loop.run_in_executor(None, _download_wechat_sync, url, title, author)
    elif url_type == 'arxiv':
        return await loop.run_in_executor(None, _download_arxiv_sync, url, title, author)
    else:
        return {"success": False, "url": url, "error": "不支持的 URL 类型"}


@mcp.tool()
async def batch_download_and_convert(
    urls: list[str],
    titles: Optional[list[str]] = None,
    authors: Optional[list[str]] = None
) -> dict:
    """批量并行下载并转换多篇文章。支持知乎专栏、微信公众号、arXiv 论文。

    Args:
        urls: 文章 URL 列表(支持知乎、微信公众号、arXiv)
        titles: 自定义标题列表(可选，与 urls 一一对应)
        authors: 自定义作者列表(可选，与 urls 一一对应)
    """
    if not urls:
        return {"success": False, "error": "URL 列表不能为空"}

    # 验证列表长度一致
    if titles and len(titles) != len(urls):
        return {"success": False, "error": "titles 列表长度必须与 urls 一致"}
    if authors and len(authors) != len(urls):
        return {"success": False, "error": "authors 列表长度必须与 urls 一致"}

    # 构建 URL 参数对
    tasks = []
    for i, url in enumerate(urls):
        url = url.strip()
        if not url:
            continue
        title = titles[i] if titles else None
        author = authors[i] if authors else None
        tasks.append(_download_single_async(url, title, author))

    if not tasks:
        return {"success": False, "error": "没有有效的 URL"}

    # 并行执行所有下载任务
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 统计结果
    success_count = 0
    failed_count = 0
    processed_results = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "success": False,
                "url": urls[i],
                "error": str(result)
            })
            failed_count += 1
        else:
            processed_results.append(result)
            if result.get("success"):
                success_count += 1
            else:
                failed_count += 1

    return {
        "success": True,
        "total": len(tasks),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": processed_results,
        "message": f"完成 {success_count}/{len(tasks)} 篇文章下载转换"
    }


@mcp.tool()
async def download_and_convert(
    url: str,
    title: Optional[str] = None,
    author: Optional[str] = None
) -> dict:
    """从 URL 自动下载文章并转换为 KFX/EPUB 格式。支持知乎专栏、微信公众号、arXiv 论文。

    Args:
        url: 文章 URL(支持知乎、微信公众号、arXiv)
        title: 自定义标题(可选)
        author: 自定义作者(可选)
    """
    url = url.strip()
    if not url:
        return {"success": False, "error": "URL 不能为空"}

    url_type = detect_url_type(url)
    if url_type == 'unknown':
        return {"success": False, "error": "不支持的 URL 类型，目前支持知乎、微信公众号、arXiv"}

    # 使用 run_in_executor 避免在 asyncio 事件循环中直接运行 Playwright 同步 API
    loop = asyncio.get_event_loop()

    if url_type == 'zhihu':
        result = await loop.run_in_executor(None, _download_zhihu_sync, url, title, author)
    elif url_type == 'wechat':
        result = await loop.run_in_executor(None, _download_wechat_sync, url, title, author)
    elif url_type == 'arxiv':
        result = await loop.run_in_executor(None, _download_arxiv_sync, url, title, author)
    else:
        result = {"success": False, "error": "不支持的 URL 类型"}

    return result


@mcp.tool()
def upload_local_file(
    file_path: str,
    title: Optional[str] = None,
    author: Optional[str] = None
) -> dict:
    """上传本地 Markdown 文件并转换为 KFX/EPUB 格式。支持从文件名或内容自动提取标题。

    Args:
        file_path: 本地 Markdown 文件的绝对路径
        title: 自定义标题(可选，默认从文件名或内容提取)
        author: 自定义作者(可选，默认为 Unknown 或从 frontmatter 提取)
    """
    return _upload_local_file_sync(file_path, title, author)


@mcp.tool()
def batch_upload_local_files(
    file_paths: list[str],
    titles: Optional[list[str]] = None,
    authors: Optional[list[str]] = None
) -> dict:
    """批量上传本地 Markdown 文件并转换为 KFX/EPUB 格式。

    Args:
        file_paths: 本地 Markdown 文件路径列表
        titles: 自定义标题列表(可选，与 file_paths 一一对应)
        authors: 自定义作者列表(可选，与 file_paths 一一对应)
    """
    return _upload_local_files_sync(file_paths, titles, authors)


@mcp.tool()
def search_files(keyword: str, check_kindle: bool = False) -> dict:
    """按关键字搜索已下载的文章文件。可以搜索标题中包含指定关键字的文件,并可选择是否检查文件是否已在 Kindle 上。

    Args:
        keyword: 搜索关键字,匹配文件标题
        check_kindle: 是否同时检查文件是否在 Kindle 上(默认 false)
    """
    keyword = keyword.strip()
    if not keyword:
        return {"success": False, "error": "关键字不能为空"}

    files = search_files_by_keyword(keyword, check_kindle)
    return {
        "success": True,
        "keyword": keyword,
        "files": files,
        "total": len(files)
    }


@mcp.tool()
def send_to_kindle(file_id: str, format: Literal["kfx", "epub"] = "kfx") -> dict:
    """将指定文件推送到墨水屏阅读器(Kindle)。需要先确保 Kindle 已连接。

    Args:
        file_id: 要推送的文件 ID
        format: 推送格式:kfx 或 epub(默认 kfx)
    """
    file_id = file_id.strip()
    if not file_id:
        return {"success": False, "error": "file_id 不能为空"}

    success, message = copy_to_kindle(file_id, format)
    return {
        "success": success,
        "file_id": file_id,
        "format": format,
        "message": message
    }


@mcp.tool()
def delete_from_kindle(file_id: str) -> dict:
    """从墨水屏阅读器(Kindle)删除指定文件及其关联的 SDR 文件夹

    Args:
        file_id: 要删除的文件 ID
    """
    file_id = file_id.strip()
    if not file_id:
        return {"success": False, "error": "file_id 不能为空"}

    success, message, deleted_items = _delete_from_kindle_impl(file_id)
    return {
        "success": success,
        "file_id": file_id,
        "message": message,
        "deleted_items": deleted_items
    }


@mcp.tool()
def list_kindle_files() -> dict:
    """列出墨水屏阅读器(Kindle)上所有的 KFX/EPUB 文件"""
    if not check_kindle_connected():
        return {"success": False, "error": "墨水屏阅读器未连接"}

    kindle_files = get_kindle_files()
    return {
        "success": True,
        "device_path": str(KINDLE_ARTICLE_PATH),
        "files": list(kindle_files),
        "total": len(kindle_files)
    }


@mcp.tool()
def list_files(
    status: Optional[Literal["uploaded", "converted", "converted_epub"]] = None,
    source: Optional[Literal["zhihu", "wechat", "arxiv", "upload"]] = None,
    limit: int = 50
) -> dict:
    """列出数据库中所有已下载的文件。可以按状态和来源过滤。

    Args:
        status: 按状态过滤:uploaded(已上传)、converted(已转换)、converted_epub(仅EPUB)
        source: 按来源过滤:zhihu、wechat、arxiv、upload
        limit: 返回结果的最大数量(默认 50,0 表示不限制)
    """
    files = list_all_files(status, source, limit)
    return {
        "success": True,
        "files": files,
        "total": len(files),
        "filters": {
            "status": status,
            "source": source,
            "limit": limit
        }
    }


@mcp.tool()
def get_file_info(file_id: str) -> dict:
    """获取指定文件的详细信息,包括转换状态、文件路径、是否在 Kindle 上等。

    Args:
        file_id: 文件 ID
    """
    file_id = file_id.strip()
    if not file_id:
        return {"success": False, "error": "file_id 不能为空"}

    detail = get_file_detail(file_id)
    if not detail:
        return {"success": False, "error": f"文件不存在: {file_id}"}

    return {"success": True, "file": detail}


@mcp.tool()
def delete_file(file_id: str, remove_from_kindle: bool = False) -> dict:
    """删除指定文件。可以同时删除本地文件和 Kindle 上的文件。

    Args:
        file_id: 要删除的文件 ID
        remove_from_kindle: 是否同时从 Kindle 删除(默认 false)
    """
    file_id = file_id.strip()
    if not file_id:
        return {"success": False, "error": "file_id 不能为空"}

    result = delete_file_complete(file_id, remove_from_kindle)
    return result


if __name__ == "__main__":
    mcp.run(transport='sse')