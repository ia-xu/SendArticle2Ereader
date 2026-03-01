#!/usr/bin/env python3
"""
Markdown to Kindle KFX Converter (Windows Compatible)
支持数学公式 (LaTeX) 和远程图片下载
"""

import os
import re
import sys
import json
import shutil
import subprocess
import tempfile
import hashlib
import requests
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# Windows 编码修复
if sys.platform == 'win32':
    import codecs
    # 强制使用 UTF-8 编码
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
    # 设置环境变量
    os.environ['PYTHONIOENCODING'] = 'utf-8'

class MarkdownToKFX:
    def __init__(self, markdown_file, output_file=None, title=None, author=None):
        self.md_file = Path(markdown_file)
        self.output_file = output_file or self.md_file.with_suffix('.kfx')
        self.title = title or self.md_file.stem
        self.author = author or "Unknown"
        self.temp_dir = Path(tempfile.mkdtemp())
        self.images_dir = self.temp_dir / "images"
        self.images_dir.mkdir(exist_ok=True)

    def download_image(self, url):
        """下载远程图片并返回本地路径"""
        try:
            parsed = urlparse(url)
            ext = Path(parsed.path).suffix or '.jpg'
            if ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']:
                ext = '.jpg'

            filename = hashlib.md5(url.encode()).hexdigest() + ext
            local_path = self.images_dir / filename

            if local_path.exists():
                return local_path

            print(f"Downloading image: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                f.write(response.content)

            # 转换 webp/svg 为 jpg/png
            if ext in ['.webp', '.svg']:
                try:
                    from PIL import Image
                    img = Image.open(local_path)
                    new_path = local_path.with_suffix('.png')
                    img.convert('RGB').save(new_path, 'PNG')
                    local_path = new_path
                except Exception as e:
                    print(f"Image conversion warning: {e}")

            return local_path

        except Exception as e:
            print(f"Failed to download {url}: {e}")
            return None

    def process_math_formulas(self, content):
        """处理数学公式"""
        inline_pattern = r'\$([^\$]+)\$'
        block_pattern = r'\$\$([^\$]+)\$\$'

        def render_math(match, display_mode=False):
            latex = match.group(1).strip()
            if display_mode:
                return f'<div class="math-block">{latex}</div>'
            else:
                return f'<span class="math-inline">{latex}</span>'

        content = re.sub(block_pattern, lambda m: render_math(m, True), content)
        content = re.sub(inline_pattern, lambda m: render_math(m, False), content)

        return content

    def markdown_to_html(self):
        """将 Markdown 转换为 HTML"""
        import markdown

        with open(self.md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        md_content = self.process_math_formulas(md_content)

        # 查找所有图片链接
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        images = re.findall(image_pattern, md_content)

        image_map = {}
        for alt_text, img_url in images:
            if img_url.startswith(('http://', 'https://')):
                local_path = self.download_image(img_url)
                if local_path:
                    rel_path = f"images/{local_path.name}"
                    image_map[img_url] = rel_path
                    md_content = md_content.replace(f"]({img_url})", f"]({rel_path})")
            elif not img_url.startswith(('/', 'data:')):
                src_path = self.md_file.parent / img_url
                if src_path.exists():
                    dest_path = self.images_dir / src_path.name
                    shutil.copy2(src_path, dest_path)
                    md_content = md_content.replace(f"]({img_url})", f"](images/{dest_path.name})")

        md = markdown.Markdown(extensions=[
            'fenced_code',
            'tables',
            'toc',
            'meta',
            'nl2br'
        ])

        html_content = md.convert(md_content)

        full_html = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta charset="UTF-8"/>
    <title>{self.title}</title>
    <style>
        body {{
            font-family: "Amazon Ember", "Noto Serif", Georgia, "SimSun", serif;
            line-height: 1.6;
            margin: 5%;
            color: #333;
        }}
        h1, h2, h3, h4, h5, h6 {{
            font-family: "Amazon Ember", "Noto Sans", Arial, "SimHei", sans-serif;
            color: #000;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 1em auto;
        }}
        .math-block {{
            text-align: center;
            margin: 1em 0;
            font-style: italic;
        }}
        .math-inline {{
            font-style: italic;
        }}
        pre {{
            background-color: #f4f4f4;
            padding: 1em;
            overflow-x: auto;
            border-radius: 4px;
        }}
        code {{
            font-family: "Courier New", monospace;
            background-color: #f4f4f4;
            padding: 0.2em 0.4em;
        }}
        blockquote {{
            border-left: 4px solid #ccc;
            margin-left: 0;
            padding-left: 1em;
            color: #666;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""

        html_file = self.temp_dir / "content.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(full_html)

        return html_file, image_map

    def create_epub(self, html_file):
        """使用 ebooklib 创建 EPUB (避免 Calibre 编码问题)"""
        try:
            from ebooklib import epub
        except ImportError:
            print("Please install ebooklib: pip install EbookLib")
            raise

        print(f"Creating EPUB using ebooklib...")

        book = epub.EpubBook()
        book.set_identifier(f"id:{self.md_file.stem}")
        book.set_title(self.title)
        book.set_language('zh-CN')
        book.add_author(self.author)

        # 读取 HTML 内容
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 创建章节
        chapter = epub.EpubHtml(title='Content', file_name='content.xhtml', lang='zh-CN')
        chapter.content = content
        book.add_item(chapter)

        # 添加图片
        for img_file in self.images_dir.iterdir():
            if img_file.is_file():
                with open(img_file, 'rb') as f:
                    img_content = f.read()

                ext = img_file.suffix.lower()
                if ext == '.jpg' or ext == '.jpeg':
                    media_type = "image/jpeg"
                elif ext == '.png':
                    media_type = "image/png"
                elif ext == '.gif':
                    media_type = "image/gif"
                else:
                    media_type = "image/jpeg"

                image = epub.EpubItem(
                    uid=img_file.name,
                    file_name=f"images/{img_file.name}",
                    media_type=media_type,
                    content=img_content
                )
                book.add_item(image)

        # 添加 CSS
        style = """
        body { font-family: "Noto Serif", Georgia, "SimSun", serif; }
        .math-block { text-align: center; margin: 1em 0; }
        """
        nav_css = epub.EpubItem(
            uid="style",
            file_name="style.css",
            media_type="text/css",
            content=style
        )
        book.add_item(nav_css)

        # 添加导航
        book.toc = (epub.Link('content.xhtml', 'Content', 'content'),)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        book.spine = ['nav', chapter]

        epub_file = self.temp_dir / "book.epub"
        epub.write_epub(str(epub_file), book, {})

        print(f"EPUB created: {epub_file}")
        return epub_file

    def epub_to_kfx(self, epub_file):
        """使用 Calibre 命令行将 EPUB 转换为 KFX"""

        # Windows 下使用 shell=True 并设置编码
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        # 首先尝试使用 ebook-convert (Calibre 的标准工具)
        ebook_convert = self._find_calibre_tool('ebook-convert.exe')

        if not ebook_convert:
            print("Error: Calibre not found. Please install Calibre first.")
            print("Download: https://calibre-ebook.com/download")
            sys.exit(1)

        print(f"Using Calibre: {ebook_convert}")

        # 使用 ebook-convert 直接转换为 KFX
        # 注意：需要安装 KFX Output 插件
        kfx_file = self.temp_dir / "book.kfx"

        cmd = [
            str(ebook_convert),
            str(epub_file),
            str(kfx_file),
            '--title', self.title,
            '--authors', self.author,
            '--language', 'zh-CN'
        ]

        try:
            print(f"Converting to KFX...")
            # Windows 下使用 creationflags 避免控制台窗口弹出
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',  # 忽略编码错误
                env=env,
                creationflags=creationflags
            )

            if result.returncode != 0:
                print(f"Conversion warning: {result.stderr}")

            # 检查是否生成 KFX
            if kfx_file.exists():
                shutil.copy2(kfx_file, self.output_file)
                print(f"KFX created: {self.output_file}")
                return self.output_file
            else:
                # 尝试查找其他输出格式
                for ext in ['.azw3', '.mobi', '.azw']:
                    alt_file = self.temp_dir / f"book{ext}"
                    if alt_file.exists():
                        final_output = self.output_file.with_suffix(ext)
                        shutil.copy2(alt_file, final_output)
                        print(f"Created {ext} instead: {final_output}")
                        return final_output

                raise FileNotFoundError("KFX file not generated")

        except Exception as e:
            print(f"KFX conversion failed: {e}")
            # 备用：返回 EPUB，用户可手动转换
            fallback = self.output_file.with_suffix('.epub')
            shutil.copy2(epub_file, fallback)
            print(f"Fallback: EPUB saved to {fallback}")
            return fallback

    def _find_calibre_tool(self, tool_name):
        """查找 Calibre 工具路径"""
        # 常见安装路径
        possible_paths = [
            Path("C:/Program Files/Calibre2") / tool_name,
            Path("C:/Program Files (x86)/Calibre2") / tool_name,
            Path(os.environ.get('LOCALAPPDATA', '')) / "Programs/Calibre" / tool_name,
        ]

        # 检查 PATH
        for path in possible_paths:
            if path.exists():
                return path

        # 使用 where 命令查找
        try:
            result = subprocess.run(['where', tool_name], capture_output=True, text=True)
            if result.returncode == 0:
                return Path(result.stdout.strip().split('\n')[0])
        except:
            pass

        return None

    def convert(self):
        """主转换流程"""
        try:
            print(f"Starting conversion: {self.md_file} -> {self.output_file}")

            # 1. Markdown -> HTML
            html_file, image_map = self.markdown_to_html()
            print(f"HTML generated with {len(image_map)} remote images downloaded")

            # 2. HTML -> EPUB (使用纯 Python，避免编码问题)
            epub_file = self.create_epub(html_file)

            # 3. EPUB -> KFX
            result_file = self.epub_to_kfx(epub_file)

            if result_file.suffix == '.kfx':
                print(f"\nSuccess! KFX file: {result_file}")
            else:
                print(f"\nPartial success: {result_file.suffix} file created")
                print("You can manually convert EPUB to KFX using Calibre")

            print(f"File size: {result_file.stat().st_size / 1024:.2f} KB")

            return result_file

        except Exception as e:
            print(f"Conversion failed: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # 清理临时文件
            try:
                shutil.rmtree(self.temp_dir)
                print(f"Cleaned up temp files")
            except:
                pass

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Convert Markdown to Kindle KFX format')
    parser.add_argument('markdown_file', help='Input Markdown file')
    parser.add_argument('-o', '--output', help='Output KFX file path')
    parser.add_argument('-t', '--title', help='Book title')
    parser.add_argument('-a', '--author', help='Book author')

    args = parser.parse_args()

    if not os.path.exists(args.markdown_file):
        print(f"Error: File not found: {args.markdown_file}")
        sys.exit(1)

    converter = MarkdownToKFX(
        args.markdown_file,
        args.output,
        args.title,
        args.author
    )

    result = converter.convert()
    sys.exit(0 if result else 1)

if __name__ == '__main__':
    main()