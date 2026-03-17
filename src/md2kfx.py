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
from tqdm.contrib.concurrent import thread_map

# 图片处理库
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

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
    def __init__(self, markdown_file, output_file=None, title=None, author=None, skip_mathml=False):
        self.md_file = Path(markdown_file).absolute()
        self.output_file = Path(output_file) if output_file else self.md_file.with_suffix('.kfx')
        self.title = title or self.md_file.stem
        self.author = author or "Unknown"
        self.skip_mathml = skip_mathml  # KFX 不支持复杂 MathML
        self.temp_dir = Path(tempfile.mkdtemp())
        self.images_dir = self.temp_dir / "images"
        self.images_dir.mkdir(exist_ok=True)
        self.toc_items = []  # 存储目录结构

    def download_image(self, url):
        """下载单个远程图片"""
        try:
            parsed = urlparse(url)
            ext = Path(parsed.path).suffix or '.jpg'
            if ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']:
                ext = '.jpg'

            filename = hashlib.md5(url.encode()).hexdigest() + ext
            local_path = self.images_dir / filename

            if local_path.exists():
                return local_path

            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                f.write(response.content)
            return local_path
        except Exception as e:
            print(f"  [Warning] Failed to download {url}: {e}")
            return None

    def download_images_parallel(self, urls):
        """并行下载多个图片，返回 url -> local_path 的映射"""
        if not urls:
            return {}

        def download_one(url):
            local_path = self.download_image(url)
            return (url, local_path)

        results = thread_map(download_one, urls, max_workers=4, desc="Downloading images", disable=len(urls) <= 1)
        return {url: path for url, path in results if path is not None}

    def convert_image_for_kindle(self, src_path, dest_dir):
        """转换图片为 Kindle 兼容格式（GIF/WebP -> PNG）"""
        src_path = Path(src_path)
        ext = src_path.suffix.lower()

        # Kindle 支持的格式
        kindle_supported = ['.jpg', '.jpeg', '.png', '.gif']

        if ext in ['.jpg', '.jpeg', '.png']:
            # 直接复制
            dest_path = dest_dir / src_path.name
            if not dest_path.exists():
                shutil.copy2(src_path, dest_path)
            return src_path.name
        elif ext in ['.gif', '.webp', '.bmp', '.tiff']:
            # 需要转换
            if HAS_PIL:
                try:
                    with Image.open(src_path) as img:
                        # 处理 GIF 动画，只取第一帧
                        if hasattr(img, 'n_frames') and img.n_frames > 1:
                            img.seek(0)
                        # 转换为 RGB 模式（去除透明度）
                        if img.mode in ('RGBA', 'P'):
                            # 创建白色背景
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                            img = background
                        elif img.mode != 'RGB':
                            img = img.convert('RGB')

                        new_name = src_path.stem + '.png'
                        dest_path = dest_dir / new_name
                        img.save(dest_path, 'PNG')
                        print(f"  [Image] Converted {src_path.name} -> {new_name}")
                        return new_name
                except Exception as e:
                    print(f"  [Warning] Failed to convert {src_path.name}: {e}")
                    # 回退：直接复制
                    dest_path = dest_dir / src_path.name
                    if not dest_path.exists():
                        shutil.copy2(src_path, dest_path)
                    return src_path.name
            else:
                # 没有 PIL，直接复制（可能会有兼容问题）
                dest_path = dest_dir / src_path.name
                if not dest_path.exists():
                    shutil.copy2(src_path, dest_path)
                return src_path.name
        else:
            # 其他格式直接复制
            dest_path = dest_dir / src_path.name
            if not dest_path.exists():
                shutil.copy2(src_path, dest_path)
            return src_path.name

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
                # 尝试使用支持中文的等宽字体（按优先级排列）
                # 注意：Microsoft YaHei Mono 不是标准字体，使用 Microsoft YaHei 或其他中文字体
                font_name = 'C:/Windows/Fonts/simhei.ttf'  # 微软雅黑（非等宽，但支持中文）

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
        """预处理：清理重影 + 修复格式错误的公式 + 处理代码块转图片 + 清理问题字符"""
        # 清理重复的公式标记（重影问题）
        content = re.sub(r'\$\$(.*?)\$\$\s*\1', r'$$\1$$', content, flags=re.DOTALL)
        content = re.sub(r'\$([^\$\n]+)\$\s*\1', r'$\1$', content)

        # 修复格式错误的公式：$...$$...$ 或 $$...$...$$ 等混合格式
        # 问题模式1: $...$$...$ (行内开始，中间有$$，行内结束)
        # 这通常是因为知乎解析错误，多个公式被合并了
        # 策略：将 $$ 替换为 $ 来分割成两个独立的行内公式
        def fix_mixed_formula(match):
            text = match.group(0)
            # 如果包含 $$ 但不是以 $$ 开始或结束
            if '$$' in text and not text.startswith('$$') and not text.endswith('$$'):
                # 将内部的 $$ 替换为分隔符
                # 例如: $A$$B$ -> $A$ $B$
                parts = text.split('$$')
                result = []
                for i, part in enumerate(parts):
                    if i == 0:
                        # 第一部分，去掉开头的 $
                        if part.startswith('$'):
                            result.append(part[1:])
                        else:
                            result.append(part)
                    elif i == len(parts) - 1:
                        # 最后一部分，去掉结尾的 $
                        if part.endswith('$'):
                            result.append(part[:-1])
                        else:
                            result.append(part)
                    else:
                        result.append(part)
                return ' $' + '$ $'.join(result) + '$ '
            return text

        # 匹配可能包含 $$ 的行内公式
        content = re.sub(r'\$[^$]*\$\$[^$]*\$', fix_mixed_formula, content)

        # 问题模式2: 独立的 $$ (不是块级公式的一部分)
        # 匹配单独出现的 $$ 且前后不是 $$ 的情况
        # 这通常意味着公式未正确闭合
        content = re.sub(r'(?<!\$)\$\$(?!\$)(?!\s*$)(?!\s*\n)', '$', content)

        # 清理可能导致 KFX 问题的特殊 Unicode 字符
        # 替换全角空格为普通空格
        content = content.replace('\u3000', ' ')
        # 替换零宽字符
        content = re.sub(r'[\u200b-\u200f\u2028-\u202f\ufeff]', '', content)
        # 替换特殊的数学符号中的不可见字符（如 U+2061 FUNCTION APPLICATION）
        content = content.replace('\u2061', '')  # function application
        content = content.replace('\u2062', '')  # invisible times
        content = content.replace('\u2063', '')  # invisible separator
        content = content.replace('\u2064', '')  # invisible plus

        # 清理多余的空行（超过2个连续空行缩减为2个）
        content = re.sub(r'\n{4,}', '\n\n\n', content)

        # 处理代码块转图片
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

        # 如果 skip_mathml 为 True，将数学公式转换为纯文本形式
        # KFX Enhanced Typesetting 不支持复杂 MathML
        if self.skip_mathml:
            # 块级公式：去掉 $$ 标记，保留内容
            content = re.sub(r'\$\$(.*?)\$\$', r'\n[\1]\n', content, flags=re.DOTALL)
            # 行内公式：去掉 $ 标记，保留内容
            content = re.sub(r'\$([^\$]+)\$', r'[\1]', content)
            return content

        try:
            import latex2mathml.converter
        except ImportError:
            return content

        # 占位符标记，用于后处理替换为 menclose 元素
        CANCEL_MARKER = '\uE001'      # \cancel
        BCANCEL_MARKER = '\uE002'     # \bcancel
        XCANCEL_MARKER = '\uE003'     # \xcancel
        END_MARKER = '\uE004'
        TAG_MARKER = '\uE005'         # \tag 编号

        def extract_braced_content(s, start):
            """从 start 位置提取匹配的大括号内容，返回 (内容, 结束位置)"""
            if start >= len(s) or s[start] != '{':
                return '', start
            depth = 0
            for i in range(start, len(s)):
                if s[i] == '{':
                    depth += 1
                elif s[i] == '}':
                    depth -= 1
                    if depth == 0:
                        return s[start+1:i], i + 1
            return s[start+1:], len(s)

        def remove_latex_command(cmd_name, latex):
            """移除带有一个花括号参数的命令，保留内容：\cmd{content} -> content"""
            pattern = r'\\' + cmd_name + r'\s*\{'
            result = []
            last_end = 0
            for m in re.finditer(pattern, latex):
                content, end = extract_braced_content(latex, m.end() - 1)
                result.append(latex[last_end:m.start()])
                result.append(content)
                last_end = end
            result.append(latex[last_end:])
            return ''.join(result)

        def remove_latex_command_two_args(cmd_name, latex):
            """移除带有两个花括号参数的命令，保留第二个参数：\cmd{arg1}{arg2} -> arg2"""
            pattern = r'\\' + cmd_name + r'\s*\{'
            result = []
            last_end = 0
            for m in re.finditer(pattern, latex):
                # 提取第一个参数
                arg1, pos = extract_braced_content(latex, m.end() - 1)
                # 跳过空格，提取第二个参数
                while pos < len(latex) and latex[pos] in ' \t\n':
                    pos += 1
                if pos < len(latex) and latex[pos] == '{':
                    arg2, end = extract_braced_content(latex, pos)
                    result.append(latex[last_end:m.start()])
                    result.append(arg2)
                    last_end = end
                else:
                    result.append(latex[last_end:m.start()])
                    last_end = m.end()
            result.append(latex[last_end:])
            return ''.join(result)

        def clean_latex_source(latex):
            # 移除 label
            latex = re.sub(r'\\label\{.*?\}', '', latex)
            # 粗体命令替换：\boldsymbol 和 \bm 都替换为 \mathbf
            latex = latex.replace(r'\boldsymbol', r'\mathbf')
            latex = re.sub(r'\\bm\s*\{', r'\\mathbf{', latex)
            # \tag{...} 转为占位符，后续显示为编号
            latex = re.sub(r'\\tag\s*\{([^}]*)\}',
                          lambda m: f'\\quad\\text{{{TAG_MARKER}({m.group(1)}){END_MARKER}}}', latex)
            # \tag*{...} 无括号版本
            latex = re.sub(r'\\tag\*\s*\{([^}]*)\}',
                          lambda m: f'\\quad\\text{{{TAG_MARKER}{m.group(1)}{END_MARKER}}}', latex)
            # \enclose{notation}{content} -> 用 menclose 标记包裹 content
            # notation 如 "downdiagonalstrike" 对应 bcancel 效果
            def replace_enclose(m):
                notation = m.group(1)
                content_start = m.end()
                content, _ = extract_braced_content(latex, content_start - 1)
                # 映射 notation 到标记
                if 'downdiagonalstrike' in notation and 'updiagonalstrike' in notation:
                    return f'\\text{{{XCANCEL_MARKER}{content}{END_MARKER}}}'
                elif 'downdiagonalstrike' in notation:
                    return f'\\text{{{BCANCEL_MARKER}{content}{END_MARKER}}}'
                elif 'updiagonalstrike' in notation:
                    return f'\\text{{{CANCEL_MARKER}{content}{END_MARKER}}}'
                else:
                    return content  # 其他类型直接保留内容
            latex = re.sub(r'\\enclose\s*\{([^}]*)\}\s*\{', replace_enclose, latex)
            # \cancel{...} 转为占位符，后续替换为 menclose
            latex = re.sub(r'\\cancel\s*\{([^}]*)\}',
                          lambda m: f'\\text{{{CANCEL_MARKER}{m.group(1)}{END_MARKER}}}', latex)
            # \bcancel{...} 转为占位符
            latex = re.sub(r'\\bcancel\s*\{([^}]*)\}',
                          lambda m: f'\\text{{{BCANCEL_MARKER}{m.group(1)}{END_MARKER}}}', latex)
            # \xcancel{...} 转为占位符
            latex = re.sub(r'\\xcancel\s*\{([^}]*)\}',
                          lambda m: f'\\text{{{XCANCEL_MARKER}{m.group(1)}{END_MARKER}}}', latex)
            # 移除颜色命令 \color{...}{...} 或 \textcolor{...}{...}，保留内容（处理嵌套）
            latex = remove_latex_command_two_args('color', latex)
            latex = remove_latex_command_two_args('textcolor', latex)
            # 移除单独的 \color{...}（无第二个参数的情况）
            latex = remove_latex_command('color', latex)
            # 移除行间距命令 [数字pt] 或 [数字]
            latex = re.sub(r'\[\d+(?:\.\d+)?(?:pt|em|ex|cm|mm)?\]', '', latex)
            # 清理 \\ 后面多余的空格
            latex = re.sub(r'\\\\\s+', r'\\\\', latex)
            return latex.strip()

        def postprocess_mathml(mathml):
            """后处理 MathML：将占位符替换为 menclose 元素"""
            # \cancel -> updiagonalstrike (正斜线 /)
            mathml = re.sub(
                f'{CANCEL_MARKER}([^{END_MARKER}]*){END_MARKER}',
                r'<menclose notation="updiagonalstrike"><mtext>\1</mtext></menclose>',
                mathml
            )
            # \bcancel -> downdiagonalstrike (反斜线 \)
            mathml = re.sub(
                f'{BCANCEL_MARKER}([^{END_MARKER}]*){END_MARKER}',
                r'<menclose notation="downdiagonalstrike"><mtext>\1</mtext></menclose>',
                mathml
            )
            # \xcancel -> updiagonalstrike downdiagonalstrike (X 形)
            mathml = re.sub(
                f'{XCANCEL_MARKER}([^{END_MARKER}]*){END_MARKER}',
                r'<menclose notation="updiagonalstrike downdiagonalstrike"><mtext>\1</mtext></menclose>',
                mathml
            )
            # \tag 编号保持原样（已经是文本形式）
            mathml = mathml.replace(TAG_MARKER, '')
            mathml = mathml.replace(END_MARKER, '')
            return mathml

        def replace_formula(match, is_block=False):
            latex_content = match.group(1)
            clean_content = clean_latex_source(latex_content)
            try:
                mathml = latex2mathml.converter.convert(clean_content)
                mathml = postprocess_mathml(mathml)
                tag = "div" if is_block else "span"
                cls = "math-block" if is_block else "math-inline"
                return f'<{tag} class="{cls}">{mathml}</{tag}>'
            except:
                return match.group(0)

        content = re.sub(r'\$\$(.*?)\$\$', lambda m: replace_formula(m, True), content, flags=re.DOTALL)

        def inline_cleanup(match):
            try:
                mathml = latex2mathml.converter.convert(clean_latex_source(match.group(1)))
                mathml = postprocess_mathml(mathml)
                return f'<span class="math-inline">{mathml}</span>'
            except:
                return match.group(0)

        content = re.sub(r'\$([^\$]+)\$', inline_cleanup, content)
        return content

    def sanitize_anchor(self, title):
        """生成仅包含 ASCII 字符的锚点，避免 KFX 转换问题"""
        # 移除中文字符和特殊标点
        # 将中文冒号、句号等替换为连字符
        title = re.sub(r'[：:。\.,，、；;！!？?【】\[\]（）()]', '-', title)
        # 移除所有非 ASCII 字符（保留字母、数字、连字符）
        anchor = re.sub(r'[^a-zA-Z0-9-]+', '-', title.lower())
        # 清理多余的连字符
        anchor = re.sub(r'-+', '-', anchor)
        anchor = re.sub(r'^-|-$', '', anchor)
        # 如果结果为空，使用 hash
        if not anchor:
            anchor = hashlib.md5(title.encode()).hexdigest()[:8]
        return anchor

    def extract_toc(self, md_content):
        """从 Markdown 内容中提取标题生成目录结构"""
        toc_items = []
        # 匹配 # 到 ###### 的标题（1-6个#）
        pattern = r'^(#{1,6})\s+(.+)$'
        # 用于追踪锚点计数，避免重复
        anchor_count = {}

        for match in re.finditer(pattern, md_content, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            # 使用 sanitize_anchor 生成 KFX 兼容的锚点 ID
            anchor = self.sanitize_anchor(title)

            # 处理锚点重复：添加序号后缀
            if anchor in anchor_count:
                anchor_count[anchor] += 1
                anchor = f"{anchor}-{anchor_count[anchor]}"
            else:
                anchor_count[anchor] = 0

            toc_items.append({
                'level': level,
                'title': title,
                'anchor': anchor
            })

        # 如果第一个标题是一级标题且在文件开头附近，跳过它（通常是文章标题）
        if toc_items and toc_items[0]['level'] == 1:
            # 检查是否在文件前100行内
            first_match = re.search(pattern, md_content, re.MULTILINE)
            if first_match and first_match.start() < 500:  # 大约前100行
                toc_items = toc_items[1:]

        return toc_items

    def generate_toc_html(self, toc_items):
        """生成目录的 HTML（正确的嵌套结构）"""
        if not toc_items:
            return ""

        html_parts = ['<div class="toc">', '<h2>目录</h2>', '<ul>']
        open_ul_count = 1  # 追踪打开的 ul 标签数量
        prev_level = 2

        for item in toc_items:
            level = item['level']

            # 处理层级变化
            if level > prev_level:
                # 进入更深层级：先关闭前一个 li，再打开新的 ul
                html_parts[-1] = html_parts[-1].replace('</li>', '')  # 移除前一个 li 的关闭标签
                for _ in range(level - prev_level):
                    html_parts.append('<ul>')
                    open_ul_count += 1
            elif level < prev_level:
                # 返回更浅层级：关闭多余的 ul 和 li
                for _ in range(prev_level - level):
                    html_parts.append('</ul></li>')
                    open_ul_count -= 1

            html_parts.append(f'<li><a href="#{item["anchor"]}">{item["title"]}</a></li>')
            prev_level = level

        # 关闭所有打开的 ul 标签
        while open_ul_count > 0:
            html_parts.append('</ul>')
            open_ul_count -= 1

        html_parts.append('</div>')
        return '\n'.join(html_parts)

    def add_anchor_ids(self, md_content):
        """为 Markdown 标题添加锚点 ID，使用已提取的 toc_items 确保锚点一致"""
        if not self.toc_items:
            return md_content

        # 创建锚点查找表：标题 -> 锚点
        # 注意：由于可能存在相同标题，需要按顺序匹配
        toc_idx = 0
        pattern = r'^(#{2,6})\s+(.+)$'

        def add_id(match):
            nonlocal toc_idx
            if toc_idx < len(self.toc_items):
                item = self.toc_items[toc_idx]
                toc_idx += 1
                level = match.group(1)
                title = match.group(2).strip()
                anchor = item['anchor']
                return f'{level} {title} {{#{anchor}}}'
            return match.group(0)

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

        # 分离远程图片和本地图片
        remote_urls = []
        for alt_text, img_url in images:
            if img_url.startswith(('http://', 'https://')):
                remote_urls.append(img_url)

        # 并行下载远程图片
        url_to_path = {}
        if remote_urls:
            url_to_path = self.download_images_parallel(remote_urls)

        # 处理所有图片引用
        for alt_text, img_url in images:
            if img_url.startswith(('http://', 'https://')):
                local_path = url_to_path.get(img_url)
                if local_path:
                    # 转换图片格式
                    converted_name = self.convert_image_for_kindle(local_path, self.images_dir)
                    md_content = md_content.replace(f"({img_url})", f"(images/{converted_name})")
            elif img_url.startswith('images/'):
                # 图片路径以 images/ 开头
                img_name = img_url[len('images/'):]  # 去掉 images/ 前缀

                # 检查图片是否已在临时目录中（如代码转图片生成的）
                if (self.images_dir / img_name).exists():
                    continue  # 已经存在，跳过

                # 从 md 文件所在目录的 images/ 子目录复制
                src_path = self.md_file.parent / 'images' / img_name
                if src_path.exists():
                    # 转换图片格式并复制
                    converted_name = self.convert_image_for_kindle(src_path, self.images_dir)
                    # 如果格式转换了，更新 md 中的引用
                    if converted_name != img_name:
                        md_content = md_content.replace(f"({img_url})", f"(images/{converted_name})")
                else:
                    print(f"  [Warning] Image not found: {src_path}")
            else:
                src_path = self.md_file.parent / img_url
                if src_path.exists():
                    converted_name = self.convert_image_for_kindle(src_path, self.images_dir)
                    md_content = md_content.replace(f"({img_url})", f"(images/{converted_name})")

        md = markdown.Markdown(extensions=['fenced_code', 'tables', 'toc', 'nl2br', 'attr_list'])
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
            print("  [Warning] Calibre ebook-convert not found, returning EPUB")
            return epub_file

        kfx_path = self.temp_dir / "output.kfx"
        cmd = [str(ebook_convert), str(epub_file), str(kfx_path), '--authors', self.author, '--title', self.title]

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(cmd, capture_output=True, creationflags=creationflags)

        if kfx_path.exists():
            shutil.copy2(kfx_path, self.output_file)
            return self.output_file
        else:
            print(f"  [Warning] KFX conversion failed")
            if result.stdout:
                print(result.stdout.decode('utf-8', errors='replace'))
            if result.stderr:
                print(result.stderr.decode('utf-8', errors='replace'))
            return epub_file

    def _find_calibre_tool(self, tool_name):
        paths = [Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / "Calibre2" / tool_name]
        for p in paths:
            if p.exists():
                return p
        return shutil.which(tool_name)

    def convert(self, keep_temp=True):
        try:
            print(f"Processing: {self.md_file.name}")
            html_file = self.markdown_to_html()
            epub_file = self.create_epub(html_file)
            final_file = self.epub_to_kfx(epub_file)
            print(f"Finished! Output: {final_file}")
            return final_file
        finally:
            if not keep_temp:
                shutil.rmtree(self.temp_dir)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Input Markdown file')
    parser.add_argument('-o', '--output', help='Output file path')
    parser.add_argument('-a', '--author', default='Kindle User', help='Author')
    parser.add_argument('--skip-mathml', action='store_true', help='Skip MathML conversion for KFX compatibility')
    args = parser.parse_args()
    if not os.path.exists(args.input):
        return
    converter = MarkdownToKFX(args.input, args.output, author=args.author, skip_mathml=args.skip_mathml)
    converter.convert()


if __name__ == '__main__':
    main()