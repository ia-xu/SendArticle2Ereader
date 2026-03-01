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

    def preprocess_md(self, content):
        """
        预处理 Markdown：专门解决知乎等平台导出的公式重影问题。
        处理逻辑：
        1. 块级公式：$$公式$$ 后面紧跟的重复公式文本
        2. 行内公式：$公式$ 后面紧跟的重复公式文本
        """
        # --- 1. 处理块级公式重影 ---
        # 匹配规律：$$\n内容\n$$\s*内容
        # 使用 re.DOTALL 允许内容跨行，\1 引用第一个括号捕获的内容
        # 注意：这里使用了 (?: ... )? 来处理可能的微小空白差异
        content = re.sub(r'\$\$(.*?)\$\$\s*\1', r'$$\1$$', content, flags=re.DOTALL)

        # --- 2. 处理行内公式重影 ---
        # 匹配规律：$公式内容$\s*公式内容
        # [^$\n]+ 确保不跨行，提高匹配准确度
        # \s* 处理 $...$ 和重复文本之间可能存在的空格
        content = re.sub(r'\$([^\$\n]+)\$\s*\1', r'$\1$', content)

        # --- 3. 补充：处理特殊的括号残留 (可选) ---
        # 有时候重影会带一点点尾巴，比如 $\mathcal{O}(n)$\mathcal{O}(n)
        # 上面的正则已经能覆盖大部分情况，如果还有顽固残留，可以加一层清理
        # content = re.sub(r'\$([^\$]+)\$\s*\\\1', r'$\1$', content)

        return content

    def process_math_formulas(self, content):

        """
        进阶版 LaTeX 处理：
        1. 支持标准 $ 和 $$ 匹配
        2. 自动清理知乎等平台导出的重复 LaTeX 后缀（如 $x$x）
        3. 转换 LaTeX 为 MathML
        """

        content = self. preprocess_md(content)

        try:
            import latex2mathml.converter
        except ImportError:
            print("Error: 'latex2mathml' not found.")
            return content

        def clean_latex_source(latex):
            """清理 LaTeX 源码中的一些特殊标记，防止转换失败"""
            latex = re.sub(r'\\label\{.*?\}', '', latex)
            # 简单处理一些常见的知乎转义错误
            latex = latex.replace(r'\boldsymbol', r'\mathbf')
            return latex.strip()

        def replace_formula(match, is_block=False):
            latex_content = match.group(1)
            clean_content = clean_latex_source(latex_content)

            try:
                mathml = latex2mathml.converter.convert(clean_content)
                tag = "div" if is_block else "span"
                cls = "math-block" if is_block else "math-inline"

                # 获取匹配项之后的文本，检查是否紧跟着相同的 LaTeX 源码（知乎重影问题）
                # 我们在主循环中处理这个更稳妥，这里先返回标记
                return f'<{tag} class="{cls}">{mathml}</{tag}>'
            except:
                return match.group(0)

        # --- 处理逻辑开始 ---

        # 1. 优先处理块级公式 $$...$$
        content = re.sub(r'\$\$(.*?)\$\$', lambda m: replace_formula(m, True), content, flags=re.DOTALL)

        # 2. 处理行内公式并清理“重影”
        # 匹配规律：$公式$紧接着相同的公式文本
        # 这个正则尝试匹配 $...$ 以及其后可能重复的相同字符
        def inline_cleanup(match):
            formula = match.group(1)
            # 转换为 MathML
            try:
                clean_f = clean_latex_source(formula)
                mathml = latex2mathml.converter.convert(clean_f)
                result = f'<span class="math-inline">{mathml}</span>'

                # 关键：检查 match 后面是否紧跟着 formula 的原文
                # 这里我们利用 re.sub 的特性，手动处理 content 的剩余部分较难
                # 采用一种取巧方案：在正则中捕获可能的重复项
                return result
            except:
                return match.group(0)

        # 改进的行内正则：捕获 $公式$ 以及后面紧跟的、非空格开始的、可能相同的文本
        # 我们先统一替换 $...$，然后用第二个正则清理掉紧随其后的 LaTeX 源码
        content = re.sub(r'\$([^\$]+)\$', inline_cleanup, content)

        # 3. 特殊清理：针对 $\mathcal{O}(n)$\mathcal{O}(n) 这种残留
        # 如果一个 HTML 标签 (</span>) 后面紧跟着一段以 \ 开头的字符，且该字符在前面出现过，则删掉它
        # 这是一个简单的启发式清理
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            # 匹配 </span>\text 这种结构并尝试清理重复
            # 这种清理比较激进，针对你给出的例子非常有效
            line = re.sub(r'(<span class="math-inline">.*?</span>)\\([a-zA-Z0-9_{}\^\\(\)\.,\s]+)', r'\1', line)
            new_lines.append(line)

        return '\n'.join(new_lines)

    def markdown_to_html(self):
        """将 Markdown 转换为 HTML，包含 MathML 注入"""
        import markdown

        with open(self.md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # 1. 首先处理 LaTeX 公式（在 Markdown 转换前处理，防止符号被转义）
        md_content = self.process_math_formulas(md_content)

        # 2. 识别并下载图片
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        images = re.findall(image_pattern, md_content)

        image_map = {}
        for alt_text, img_url in images:
            if img_url.startswith(('http://', 'https://')):
                local_path = self.download_image(img_url)
                if local_path:
                    rel_path = f"images/{local_path.name}"
                    md_content = md_content.replace(f"({img_url})", f"({rel_path})")
                    image_map[img_url] = rel_path
            else:
                # 处理本地相对路径图片
                src_path = self.md_file.parent / img_url
                if src_path.exists():
                    dest_path = self.images_dir / src_path.name
                    shutil.copy2(src_path, dest_path)
                    md_content = md_content.replace(f"({img_url})", f"(images/{src_path.name})")

        # 3. 转换为 HTML
        md = markdown.Markdown(extensions=['fenced_code', 'tables', 'toc', 'nl2br'])
        html_body = md.convert(md_content)

        full_html = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta charset="UTF-8"/>
    <title>{self.title}</title>
    <style>
        body {{ font-family: "Noto Serif", serif; line-height: 1.6; margin: 5%; }}
        h1, h2, h3 {{ color: #111; }}
        img {{ max-width: 100%; height: auto; display: block; margin: 1em auto; }}
        .math-block {{ text-align: center; margin: 1.5em 0; overflow-x: auto; }}
        .math-inline {{ vertical-align: middle; }}
        pre {{ background: #f4f4f4; padding: 1em; border-radius: 4px; font-size: 0.9em; }}
        blockquote {{ border-left: 4px solid #ddd; padding-left: 1em; color: #555; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; }}
    </style>
</head>
<body>
    {html_body}
</body>
</html>"""

        html_file = self.temp_dir / "content.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(full_html)

        return html_file

    def create_epub(self, html_file):
        """创建 EPUB 文件 (使用 ebooklib)"""
        from ebooklib import epub

        book = epub.EpubBook()
        book.set_identifier(f"id_{hashlib.md5(self.title.encode()).hexdigest()}")
        book.set_title(self.title)
        book.set_language('zh-CN')
        book.add_author(self.author)

        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # 创建章节，必须是 .xhtml 扩展名以支持 MathML
        chapter = epub.EpubHtml(title='Main Content', file_name='content.xhtml', lang='zh-CN')
        chapter.content = html_content
        book.add_item(chapter)

        # 打包图片到 EPUB
        for img_file in self.images_dir.iterdir():
            if img_file.is_file():
                with open(img_file, 'rb') as f:
                    content = f.read()

                # 确定 MIME 类型
                ext = img_file.suffix.lower()
                mime = "image/jpeg"
                if ext == '.png':
                    mime = "image/png"
                elif ext == '.gif':
                    mime = "image/gif"

                item = epub.EpubItem(uid=img_file.stem, file_name=f"images/{img_file.name}",
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
        """调用 Calibre 将 EPUB 转为 KFX"""
        ebook_convert = self._find_calibre_tool('ebook-convert.exe')
        if not ebook_convert:
            print("Error: Calibre ebook-convert not found. Make sure Calibre is installed.")
            return epub_file  # 返回 EPUB 作为备选

        print(f"  [Calibre] Converting to KFX...")
        # kfx_path = self.temp_dir / "output.kfx"
        kfx_path = self.temp_dir / "output.kfx"

        cmd = [
            str(ebook_convert),
            str(epub_file),
            str(kfx_path),
            '--authors', self.author,
            '--title', self.title,
            '--language', 'zh'
        ]

        try:
            # Windows 下隐藏窗口运行
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            subprocess.run(cmd, capture_output=True, creationflags=creationflags)

            if kfx_path.exists():
                shutil.copy2(kfx_path, self.output_file)
                shutil.copy2(epub_file, self.output_file.with_suffix('.epub'))

                return self.output_file
        except Exception as e:
            print(f"  [Error] Calibre conversion failed: {e}")

        # 兜底：如果 KFX 失败，尝试导出为 AZW3 或保持 EPUB
        fallback = self.output_file.with_suffix('.epub')
        shutil.copy2(epub_file, fallback)
        return fallback

    def _find_calibre_tool(self, tool_name):
        # 搜索 Calibre 常用安装路径
        paths = [
            Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / "Calibre2" / tool_name,
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')) / "Calibre2" / tool_name,
        ]
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

    if not os.path.exists(args.input):
        print("Input file not found.")
        return

    converter = MarkdownToKFX(args.input, args.output, author=args.author)
    converter.convert()


if __name__ == '__main__':
    main()