import os
import re
import sys
import json
import shutil
import hashlib
import requests
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup


# --- 核心依赖说明 ---
# pip install markdown ebooklib requests beautifulsoup4 latex2mathml
# ------------------

class MarkdownToEPUB3:
    def __init__(self, markdown_file, output_file=None, title=None, author=None):
        self.md_file = Path(markdown_file).absolute()
        # 强制输出为 .epub
        self.output_file = Path(output_file) if output_file else self.md_file.with_suffix('.epub')
        self.title = title or self.md_file.stem
        self.author = author or "Kindle User"
        self.temp_dir = Path(tempfile.mkdtemp())
        self.images_dir = self.temp_dir / "images"
        self.images_dir.mkdir(exist_ok=True)

    def download_image(self, url):
        """下载远程图片并返回本地路径"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            parsed = urlparse(url)
            ext = Path(parsed.path).suffix or '.jpg'
            filename = hashlib.md5(url.encode()).hexdigest() + ext
            local_path = self.images_dir / filename

            if local_path.exists(): return local_path

            print(f"  [Image] Downloading: {url}")
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(response.content)
            return local_path
        except Exception as e:
            print(f"  [Warning] Failed to download {url}: {e}")
            return None

    def preprocess_math(self, content):
        """处理知乎公式重影及 LaTeX 转换"""
        # 1. 清理重影 (你的原始逻辑非常棒)
        content = re.sub(r'\$\$(.*?)\$\$\s*\1', r'$$\1$$', content, flags=re.DOTALL)
        content = re.sub(r'\$([^\$\n]+)\$\s*\1', r'$\1$', content)

        try:
            import latex2mathml.converter
        except ImportError:
            print("Error: 'latex2mathml' not found. Formulas will not render.")
            return content

        def to_mathml(match, is_block=False):
            latex = match.group(1).strip()
            # 简单清理知乎常见错误
            latex = latex.replace(r'\boldsymbol', r'\mathbf').replace(r'\oiint', r'\int')
            try:
                mathml = latex2mathml.converter.convert(latex)
                if is_block:
                    return f'<div class="math-block">{mathml}</div>'
                return f'<span class="math-inline">{mathml}</span>'
            except:
                return match.group(0)

        # 先块后行内
        content = re.sub(r'\$\$(.*?)\$\$', lambda m: to_mathml(m, True), content, flags=re.DOTALL)
        content = re.sub(r'\$([^\$]+)\$', lambda m: to_mathml(m, False), content)
        return content

    def markdown_to_html_body(self):
        """将 MD 转换为 HTML 片段"""
        import markdown
        with open(self.md_file, 'r', encoding='utf-8') as f:
            md_text = f.read()

        md_text = self.preprocess_math(md_text)

        # 图片链接处理
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

        def img_repl(match):
            alt, url = match.groups()
            if url.startswith('http'):
                local = self.download_image(url)
                return f'![{alt}](images/{local.name})' if local else f'![{alt}]({url})'
            return match.group(0)

        md_text = re.sub(image_pattern, img_repl, md_text)

        md = markdown.Markdown(extensions=['fenced_code', 'tables', 'toc', 'nl2br'])
        return md.convert(md_text)

    def markdown_to_html_body(self):
        """将 MD 转换为 HTML 片段，并强制修复 MathML 转义问题"""
        import markdown
        with open(self.md_file, 'r', encoding='utf-8') as f:
            md_text = f.read()

        md_text = self.preprocess_math(md_text)

        # 转换 Markdown
        md = markdown.Markdown(extensions=['fenced_code', 'tables', 'toc', 'nl2br'])
        html_body = md.convert(md_text)

        # [关键修复]：使用 BeautifulSoup 重新清理 MathML，防止未转义符号
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_body, 'html.parser')

        # 移除知乎可能残留的非法属性
        for tag in soup.find_all(True):
            if tag.has_attr('content_id'): del tag['content_id']
            if tag.has_attr('zhida_source'): del tag['zhida_source']

        return str(soup)

    def create_epub3(self):
        """最终修复版：生成 EPUB 3 并绕过 lxml 导航解析错误"""
        from ebooklib import epub

        book = epub.EpubBook()
        book.set_identifier(hashlib.md5(self.title.encode()).hexdigest())
        book.set_title(self.title)
        book.set_language('zh-CN')
        book.add_author(self.author)

        # 1. 样式表 (保持不变)
        style = 'body { font-family: "Noto Serif SC", serif; margin: 5%; }'  # 简化版
        css_item = epub.EpubItem(uid="style_main", file_name="style/main.css", media_type="text/css", content=style)
        book.add_item(css_item)

        # 2. 生成并深度清理 HTML 内容
        html_body = self.markdown_to_html_body()

        # 3. 构造严格的 XHTML
        chapter = epub.EpubHtml(title=self.title, file_name='content.xhtml', lang='zh-CN')

        # 包装完整的 XHTML 结构
        full_xhtml = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <meta charset="utf-8" />
    <title>{self.title}</title>
    <link rel="stylesheet" href="style/main.css" type="text/css" />
</head>
<body>
    <section epub:type="chapter">
        <h1>{self.title}</h1>
        {html_body}
    </section>
</body>
</html>'''

        chapter.set_content(full_xhtml.encode('utf-8'))  # 强制字节码写入
        book.add_item(chapter)

        # 4. 编排结构 - 关键点：手动指定 TOC，不要让 ebooklib 自动从 HTML 中提取
        book.toc = (epub.Link('content.xhtml', self.title, 'intro'),)
        book.spine = ['nav', chapter]

        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # 5. 最终写入尝试
        print(f"  [EPUB3] Packaging into {self.output_file}...")
        try:
            # 增加 epub3_pages=False 选项，有些版本的 ebooklib 会在这里卡死
            epub.write_epub(str(self.output_file), book, {"epub3_pages": False})
        except Exception as e:
            print(f"  [Retry] Primary write failed, trying simplified mode: {e}")
            # 如果还报错，移除 EpubNav 这种需要解析 HTML 的组件
            book.items = [i for i in book.items if not isinstance(i, epub.EpubNav)]
            epub.write_epub(str(self.output_file), book, {})

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        return self.output_file
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Markdown file from Zhihu')
    args = parser.parse_args()

    if os.path.exists(args.input):
        converter = MarkdownToEPUB3(args.input)
        converter.create_epub3()
        print("Done! You can now 'Send to Kindle' via Email.")
    else:
        print("File not found.")