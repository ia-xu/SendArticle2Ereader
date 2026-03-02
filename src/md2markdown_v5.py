"""
Markdown to KFX Converter V5 - 带目录功能
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

# --- 新增依赖 ---
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import ImageFormatter

    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

# Windows 编码修复
if sys.platform == 'win32':
    import codecs

    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
    os.environ['PYTHONIOENCODING'] = 'utf-8'


class MarkdownToKFX:
    def __init__(self, markdown_file, output_file=None, title=None, author=None):
        self.md_file = Path(markdown_file).absolute()
        self.output_file = Path(output_file) if output_file else self.md_file.with_suffix('.kfx')
        self.title = title or self.md_file.stem
        self.author = author or "Unknown"
        self.temp_dir = Path(tempfile.mkdtemp())
        self.images_dir = self.temp_dir / "images"
        self.images_dir.mkdir(exist_ok=True)
        self.toc_items = []  # 存储目录结构

    def download_image(self, url):
        """下载远程图片"""
        try:
            parsed = urlparse(url)
            ext = Path(parsed.path).suffix or '.jpg'
            if ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']:
                ext = '.jpg'

            filename = hashlib.md5(url.encode()).hexdigest() + ext
            local_path = self.images_dir / filename

            if local_path.exists():
                return local_path

            print(f"  [Image] Downloading: {url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                f.write(response.content)
            return local_path
        except Exception as e:
            print(f"  [Warning] Failed to download {url}: {e}")
            return None

    def split_code_into_segments(self, code, lang, max_lines=30):
        """将长代码分割成多个片段，每段约 max_lines 行或按函数划分"""
        lines = code.split('\n')
        total_lines = len(lines)

        # 如果代码不长，直接返回
        if total_lines <= max_lines:
            return [code]

        segments = []

        # 尝试按函数/类定义分割
        func_patterns = [
            r'^(def\s+\w+)',           # Python 函数
            r'^(class\s+\w+)',         # 类定义
            r'^(function\s+\w+)',      # JS 函数
            r'^(\w+\s*\(.*?\)\s*{)',   # C/Java 风格函数
            r'^(const|let|var)\s+\w+\s*=\s*(?:async\s+)?(?:\([^)]*\)|\w+)\s*=>',  # 箭头函数
            r'^(public|private|protected)?\s*(static\s+)?\w+\s+\w+\s*\(',  # Java/C# 方法
        ]

        # 找到所有函数/类的起始行
        func_boundaries = []
        for i, line in enumerate(lines):
            for pattern in func_patterns:
                if re.match(pattern, line.strip()):
                    func_boundaries.append(i)
                    break

        # 添加末尾作为最后一个边界
        func_boundaries.append(total_lines)

        # 按函数边界分割，但如果单个函数太长则进一步拆分
        for i, boundary in enumerate(func_boundaries[:-1]):
            next_boundary = func_boundaries[i + 1]
            segment_lines = lines[boundary:next_boundary]
            segment_len = len(segment_lines)

            if segment_len <= max_lines:
                segments.append('\n'.join(segment_lines))
            elif segment_len > max_lines * 1.5:
                for j in range(0, segment_len, max_lines):
                    chunk = segment_lines[j:j + max_lines]
                    segments.append('\n'.join(chunk))
            else:
                segments.append('\n'.join(segment_lines))

        # 如果没有找到函数边界，则简单按行分割
        if not func_boundaries or func_boundaries == [total_lines]:
            segments = []
            for i in range(0, total_lines, max_lines):
                chunk = lines[i:i + max_lines]
                segments.append('\n'.join(chunk))

        return segments

    def code_to_image(self, code, lang):
        """将代码块转换为图片 (白底黑字版本)
        如果代码太长，返回多个图片路径的列表
        """
        if not HAS_PYGMENTS:
            return None

        try:
            try:
                lexer = get_lexer_by_name(lang or 'text')
            except:
                lexer = guess_lexer(code)

            # 检测是否包含中文字符，如果包含则使用中文字体
            has_chinese = bool(re.search(r'[\u4e00-\u9fff]', code))
            # Windows 上优先使用支持中文的字体
            if has_chinese:
                # 尝试使用支持中文的等宽字体
                font_name = 'Microsoft YaHei Mono'  # 微软雅黑等宽
            else:
                font_name = 'Consolas'

            segments = self.split_code_into_segments(code, lang, max_lines=30)

            if len(segments) == 1:
                formatter = ImageFormatter(
                    font_name=font_name,
                    font_size=16,
                    line_numbers=True,
                    style='default',
                    line_number_bg='#f0f0f0',
                    line_number_fg='#333333'
                )
                filename = f"code_{hashlib.md5(code.encode()).hexdigest()}.png"
                local_path = self.images_dir / filename
                with open(local_path, 'wb') as f:
                    f.write(highlight(code, lexer, formatter))
                return [f"images/{filename}"]
            else:
                image_paths = []
                for i, segment in enumerate(segments):
                    formatter = ImageFormatter(
                        font_name=font_name,
                        font_size=16,
                        line_numbers=True,
                        style='default',
                        line_number_bg='#f0f0f0',
                        line_number_fg='#333333'
                    )
                    segment_hash = hashlib.md5(f"{code}_{i}".encode()).hexdigest()
                    filename = f"code_{segment_hash}_part{i+1}.png"
                    local_path = self.images_dir / filename
                    with open(local_path, 'wb') as f:
                        f.write(highlight(segment, lexer, formatter))
                    image_paths.append(f"images/{filename}")
                return image_paths
        except Exception as e:
            print(f"  [Warning] Code to Image failed: {e}")
            return None

    def preprocess_md(self, content):
        """预处理：清理重影 + 处理代码块转图片"""
        content = re.sub(r'\$\$(.*?)\$\$\s*\1', r'$$\1$$', content, flags=re.DOTALL)
        content = re.sub(r'\$([^\$\n]+)\$\s*\1', r'$\1$', content)

        def code_replacer(match):
            lang = match.group(1) or ""
            code = match.group(2).strip()
            img_rel_paths = self.code_to_image(code, lang)
            if img_rel_paths:
                result = []
                for img_path in img_rel_paths:
                    result.append(f"\n![code_block]({img_path})\n")
                return '\n'.join(result)
            return match.group(0)

        content = re.sub(r'```(.*?)\n(.*?)\n```', code_replacer, content, flags=re.DOTALL)
        return content

    def process_math_formulas(self, content):
        """MathML 转换逻辑"""
        content = self.preprocess_md(content)
        try:
            import latex2mathml.converter
        except ImportError:
            return content

        def clean_latex_source(latex):
            latex = re.sub(r'\\label\{.*?\}', '', latex)
            latex = latex.replace(r'\boldsymbol', r'\mathbf')
            return latex.strip()

        def replace_formula(match, is_block=False):
            latex_content = match.group(1)
            clean_content = clean_latex_source(latex_content)
            try:
                mathml = latex2mathml.converter.convert(clean_content)
                tag = "div" if is_block else "span"
                cls = "math-block" if is_block else "math-inline"
                return f'<{tag} class="{cls}">{mathml}</{tag}>'
            except:
                return match.group(0)

        content = re.sub(r'\$\$(.*?)\$\$', lambda m: replace_formula(m, True), content, flags=re.DOTALL)

        def inline_cleanup(match):
            try:
                mathml = latex2mathml.converter.convert(clean_latex_source(match.group(1)))
                return f'<span class="math-inline">{mathml}</span>'
            except:
                return match.group(0)

        content = re.sub(r'\$([^\$]+)\$', inline_cleanup, content)
        return content

    def extract_toc(self, md_content):
        """从 Markdown 内容中提取标题生成目录结构"""
        toc_items = []
        # 匹配 ## 到 ###### 的标题
        pattern = r'^(#{2,6})\s+(.+)$'

        for match in re.finditer(pattern, md_content, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            # 生成锚点 ID（支持中文）
            anchor = re.sub(r'[^\w\u4e00-\u9fff-]+', '-', title.lower())
            anchor = re.sub(r'^-|-$', '', anchor)

            toc_items.append({
                'level': level,
                'title': title,
                'anchor': anchor
            })

        return toc_items

    def generate_toc_html(self, toc_items):
        """生成目录的 HTML"""
        if not toc_items:
            return ""

        html_parts = ['<div class="toc">', '<h2>目录</h2>', '<ul>']

        prev_level = 2
        for item in toc_items:
            level = item['level']

            # 处理层级变化
            if level > prev_level:
                for _ in range(level - prev_level):
                    html_parts.append('<ul>')
            elif level < prev_level:
                for _ in range(prev_level - level):
                    html_parts.append('</ul>')

            html_parts.append(f'<li><a href="#{item["anchor"]}">{item["title"]}</a></li>')
            prev_level = level

        # 关闭所有打开的 ul 标签
        while prev_level > 2:
            html_parts.append('</ul>')
            prev_level -= 1

        html_parts.append('</ul></div>')
        return '\n'.join(html_parts)

    def add_anchor_ids(self, md_content):
        """为 Markdown 标题添加锚点 ID"""
        def add_id(match):
            level = match.group(1)
            title = match.group(2).strip()
            anchor = re.sub(r'[^\w\u4e00-\u9fff-]+', '-', title.lower())
            anchor = re.sub(r'^-|-$', '', anchor)
            return f'{level} {title} {{#{anchor}}}'

        pattern = r'^(#{2,6})\s+(.+)$'
        return re.sub(pattern, add_id, md_content, flags=re.MULTILINE)

    def markdown_to_html(self):
        """Markdown -> HTML"""
        import markdown

        with open(self.md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        md_content = self.process_math_formulas(md_content)

        # 提取目录结构
        self.toc_items = self.extract_toc(md_content)

        # 为标题添加锚点 ID
        md_content = self.add_anchor_ids(md_content)

        # 生成目录 HTML
        toc_html = self.generate_toc_html(self.toc_items)

        # 识别并处理图片
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        images = re.findall(image_pattern, md_content)

        for alt_text, img_url in images:
            if img_url.startswith(('http://', 'https://')):
                local_path = self.download_image(img_url)
                if local_path:
                    md_content = md_content.replace(f"({img_url})", f"(images/{local_path.name})")
            elif img_url.startswith('images/'):
                pass
            else:
                src_path = self.md_file.parent / img_url
                if src_path.exists():
                    dest_path = self.images_dir / src_path.name
                    shutil.copy2(src_path, dest_path)
                    md_content = md_content.replace(f"({img_url})", f"(images/{src_path.name})")

        md = markdown.Markdown(extensions=['fenced_code', 'tables', 'toc', 'nl2br'])
        html_body = md.convert(md_content)

        full_html = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta charset="UTF-8"/>
    <title>{self.title}</title>
    <style>
        body {{ font-family: "Noto Serif", "Noto Sans CJK SC", serif; line-height: 1.6; margin: 5%; }}
        img {{ max-width: 100%; height: auto; display: block; margin: 1.2em auto; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .math-block {{ text-align: center; margin: 1.5em 0; }}
        pre {{ background: #f4f4f4; padding: 1em; border-radius: 4px; white-space: pre-wrap; }}
        .toc {{ background: #f8f9fa; padding: 1.5em; border-radius: 8px; margin-bottom: 2em; border: 1px solid #e9ecef; }}
        .toc h2 {{ margin-top: 0; margin-bottom: 1em; color: #333; border-bottom: 1px solid #dee2e6; padding-bottom: 0.5em; }}
        .toc ul {{ list-style: none; padding-left: 0; margin: 0; }}
        .toc li {{ margin: 0.3em 0; }}
        .toc a {{ color: #4a90d9; text-decoration: none; }}
        .toc a:hover {{ text-decoration: underline; }}
        .toc ul ul {{ padding-left: 1.5em; margin-top: 0.3em; }}
        h2, h3, h4, h5, h6 {{ color: #333; margin-top: 1.5em; }}
    </style>
</head>
<body>
{toc_html}
{html_body}
</body>
</html>"""

        html_file = self.temp_dir / "content.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(full_html)
        return html_file

    def create_epub(self, html_file):
        """打包 EPUB"""
        from ebooklib import epub
        book = epub.EpubBook()
        book.set_identifier(f"id_{hashlib.md5(self.title.encode()).hexdigest()}")
        book.set_title(self.title)
        book.set_language('zh-CN')
        book.add_author(self.author)

        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        chapter = epub.EpubHtml(title='Main Content', file_name='content.xhtml', lang='zh-CN')
        chapter.content = html_content
        book.add_item(chapter)

        # 添加图片
        for img_file in self.images_dir.iterdir():
            if img_file.is_file():
                with open(img_file, 'rb') as f:
                    content = f.read()
                ext = img_file.suffix.lower()
                mime = "image/png" if ext == ".png" else "image/jpeg"
                item = epub.EpubItem(uid=re.sub(r'\W+', '', img_file.stem),
                                     file_name=f"images/{img_file.name}",
                                     media_type=mime, content=content)
                book.add_item(item)

        # 生成 EPUB 目录（基于提取的标题）
        if self.toc_items:
            toc_links = []
            for item in self.toc_items:
                # 根据 level 添加缩进效果（通过标题前缀）
                indent = "  " * (item['level'] - 2)
                toc_links.append(epub.Link(f'content.xhtml#{item["anchor"]}', f'{indent}{item["title"]}', item["anchor"]))
            book.toc = tuple(toc_links)
        else:
            book.toc = (epub.Link('content.xhtml', 'Content', 'intro'),)

        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ['nav', chapter]

        epub_file = self.temp_dir / "book.epub"
        epub.write_epub(str(epub_file), book, {})
        return epub_file

    def epub_to_kfx(self, epub_file):
        """调用 Calibre 转换为 KFX"""
        ebook_convert = self._find_calibre_tool('ebook-convert.exe')
        if not ebook_convert:
            return epub_file

        kfx_path = self.temp_dir / "output.kfx"
        cmd = [str(ebook_convert), str(epub_file), str(kfx_path), '--authors', self.author, '--title', self.title]

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            subprocess.run(cmd, capture_output=True, creationflags=creationflags)
            if kfx_path.exists():
                shutil.copy2(kfx_path, self.output_file)
                return self.output_file
        except:
            pass
        return epub_file

    def _find_calibre_tool(self, tool_name):
        paths = [Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / "Calibre2" / tool_name]
        for p in paths:
            if p.exists():
                return p
        return shutil.which(tool_name)

    def convert(self):
        try:
            print(f"Processing: {self.md_file.name}")
            html_file = self.markdown_to_html()
            epub_file = self.create_epub(html_file)
            final_file = self.epub_to_kfx(epub_file)
            print(f"Finished! Output: {final_file}")
            return final_file
        finally:
            shutil.rmtree(self.temp_dir)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Input Markdown file')
    parser.add_argument('-o', '--output', help='Output file path')
    parser.add_argument('-a', '--author', default='Kindle User', help='Author')
    args = parser.parse_args()
    if not os.path.exists(args.input):
        return
    converter = MarkdownToKFX(args.input, args.output, author=args.author)
    converter.convert()


if __name__ == '__main__':
    main()