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
from urllib.parse import urlparse, unquote
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
        current_start = 0

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
                # 函数长度合适
                segments.append('\n'.join(segment_lines))
            elif segment_len > max_lines * 1.5:
                # 函数太长，按 max_lines 进一步拆分
                for j in range(0, segment_len, max_lines):
                    chunk = segment_lines[j:j + max_lines]
                    segments.append('\n'.join(chunk))
            else:
                # 稍微超过 max_lines，保持完整
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
            # 选择词法分析器
            try:
                lexer = get_lexer_by_name(lang or 'text')
            except:
                lexer = guess_lexer(code)

            # 先尝试将代码分段
            segments = self.split_code_into_segments(code, lang, max_lines=30)

            if len(segments) == 1:
                # 代码不长，单张图片
                formatter = ImageFormatter(
                    font_name='Consolas',
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
                # 长代码，生成多张图片
                image_paths = []
                for i, segment in enumerate(segments):
                    formatter = ImageFormatter(
                        font_name='Consolas',
                        font_size=16,
                        line_numbers=True,
                        style='default',
                        line_number_bg='#f0f0f0',
                        line_number_fg='#333333'
                    )
                    # 使用段索引生成唯一文件名
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
        """预处理：清理重影 + 处理知乎公式 + 处理代码块转图片"""
        # 1. 清理知乎公式重影 (保留你原有的逻辑)
        content = re.sub(r'\$\$(.*?)\$\$\s*\1', r'$$\1$$', content, flags=re.DOTALL)
        content = re.sub(r'\$([^\$\n]+)\$\s*\1', r'$\1$', content)

        # 2. 处理知乎公式图片链接（zhihu.com/equation?tex=...）转为 LaTeX 格式
        def zhihu_equation_replacer(match):
            tex_encoded = match.group(1)
            # URL 解码，将 + 替换为空格
            latex = unquote(tex_encoded.replace('+', ' '))
            return f'\n$${latex}$$\n'

        content = re.sub(
            r'!\[\]\(https?://(?:www\.)?zhihu\.com/equation\?tex=([^)]+)\)',
            zhihu_equation_replacer,
            content
        )

        # 3. 识别代码块并转为图片
        def code_replacer(match):
            lang = match.group(1) or ""
            code = match.group(2).strip()

            # 尝试转图片
            img_rel_paths = self.code_to_image(code, lang)
            if img_rel_paths:
                # 返回多个 Markdown 图片语法（长代码会生成多张图片）
                result = []
                for img_path in img_rel_paths:
                    result.append(f"\n![code_block]({img_path})\n")
                return '\n'.join(result)
            return match.group(0)  # 失败则保持原样

        # 匹配 ```lang \n code \n ```
        content = re.sub(r'```(.*?)\n(.*?)\n```', code_replacer, content, flags=re.DOTALL)

        return content

    def process_math_formulas(self, content):
        """MathML 转换逻辑 (保持原样)"""
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

    def markdown_to_html(self):
        """Markdown -> HTML"""
        import markdown

        with open(self.md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        md_content = self.process_math_formulas(md_content)

        # 识别并处理图片 (包含新生成的代码图片)
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        images = re.findall(image_pattern, md_content)

        for alt_text, img_url in images:
            if img_url.startswith(('http://', 'https://')):
                local_path = self.download_image(img_url)
                if local_path:
                    md_content = md_content.replace(f"({img_url})", f"(images/{local_path.name})")
            elif img_url.startswith('images/'):
                # 已经是本地生成的图片，不做处理
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
    </style>
</head>
<body>{html_body}</body>
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

        # 关键：将所有图片（包括下载的和代码生成的）放入 EPUB
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

        book.toc = (epub.Link('content.xhtml', 'Content', 'intro'),)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ['nav', chapter]

        epub_file = self.temp_dir / "book.epub"
        epub.write_epub(str(epub_file), book, {})
        return epub_file

    def epub_to_kfx(self, epub_file):
        """调用 Calibre (保持原样)"""
        ebook_convert = self._find_calibre_tool('ebook-convert.exe')
        if not ebook_convert: return epub_file

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
            if p.exists(): return p
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
    if not os.path.exists(args.input): return
    converter = MarkdownToKFX(args.input, args.output, author=args.author)
    converter.convert()


if __name__ == '__main__':
    main()