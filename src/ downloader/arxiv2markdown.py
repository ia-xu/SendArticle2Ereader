"""
arXiv HTML 页面转 Markdown 工具

支持：
- 从 arxiv.org/html/ 页面获取论文内容
- 转换 LaTeX HTML 格式为 Markdown
- 保留数学公式（LaTeX 格式）
- 提取标题、作者、摘要等信息
- 无需登录
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote

import requests
from bs4 import BeautifulSoup, NavigableString

# Windows 编码修复
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer') and not isinstance(sys.stdout, codecs.StreamWriter):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    if hasattr(sys.stderr, 'buffer') and not isinstance(sys.stderr, codecs.StreamWriter):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
    os.environ['PYTHONIOENCODING'] = 'utf-8'


class ArxivClient:
    """arXiv 客户端，处理页面请求"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })

    def fetch_page(self, url: str, timeout: int = 30) -> Optional[str]:
        """
        获取 arXiv HTML 页面内容

        Args:
            url: arXiv HTML 页面 URL (如 https://arxiv.org/html/2602.02276v1)
            timeout: 请求超时时间

        Returns:
            HTML 内容字符串，失败返回 None
        """
        try:
            # 标准化 URL
            if not url.startswith('http'):
                url = 'https://' + url

            # 确保是 arxiv.org/html/ 格式
            if 'arxiv.org/abs/' in url:
                # 转换 abs 链接为 html 链接
                url = url.replace('arxiv.org/abs/', 'arxiv.org/html/')

            print(f"[arXiv] Fetching: {url}")
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = 'utf-8'

            return resp.text

        except requests.RequestException as e:
            print(f"[Error] Failed to fetch page: {e}")
            return None

    def extract_article_id(self, url: str) -> Optional[str]:
        """从 URL 中提取文章 ID"""
        # 匹配格式如: 2602.02276v1 或 2602.02276
        patterns = [
            r'arxiv\.org/html/(\d+\.\d+(?:v\d+)?)',
            r'arxiv\.org/abs/(\d+\.\d+(?:v\d+)?)',
            r'(\d{4}\.\d{4,5}(?:v\d+)?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None


class ArxivToMarkdown:
    """arXiv HTML 转 Markdown"""

    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = ArxivClient()

    def convert(self, url: str, custom_title: str = None, custom_author: str = None) -> Tuple[bool, str, str]:
        """
        转换 arXiv HTML 页面为 Markdown

        Args:
            url: arXiv HTML 页面 URL
            custom_title: 自定义标题
            custom_author: 自定义作者

        Returns:
            (success, markdown_content, file_path)
        """
        # 获取页面内容
        html = self.client.fetch_page(url)
        if not html:
            return False, "", ""

        # 解析 HTML
        soup = BeautifulSoup(html, 'html.parser')

        # 提取元数据
        article_id = self.client.extract_article_id(url) or "unknown"
        title = custom_title or self._extract_title(soup)
        authors = custom_author or self._extract_authors(soup)
        abstract = self._extract_abstract(soup)

        # 转换正文
        body_content = self._convert_body(soup)

        # 构建 Markdown
        markdown = self._build_markdown(title, authors, abstract, body_content, url, article_id)

        # 保存文件
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
        filename = f"{safe_title}_{article_id}.md"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown)

        print(f"[Success] Saved to: {filepath}")
        return True, markdown, str(filepath)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取标题"""
        # 尝试多种选择器
        selectors = [
            'h1.ltx_title',
            'h1.title',
            'h1[class*="title"]',
            '.ltx_title_document h1',
            'h1',
        ]

        for selector in selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                # 移除编号等前缀
                text = title_elem.get_text().strip()
                # 移除常见的标题前缀
                text = re.sub(r'^\d+\.\s*', '', text)
                return text

        return "Untitled"

    def _extract_authors(self, soup: BeautifulSoup) -> str:
        """提取作者列表"""
        # arXiv HTML 格式的作者
        authors_elem = soup.select_one('.ltx_authors')
        if authors_elem:
            authors = []
            for author in authors_elem.select('.ltx_author'):
                name = author.get_text().strip()
                # 清理多余空白
                name = re.sub(r'\s+', ' ', name)
                if name:
                    authors.append(name)
            return ', '.join(authors) if authors else 'Unknown'

        # 备用选择器
        authors_elem = soup.select_one('.authors')
        if authors_elem:
            return authors_elem.get_text().strip()

        return 'Unknown'

    def _extract_abstract(self, soup: BeautifulSoup) -> str:
        """提取摘要"""
        # arXiv HTML 格式
        abstract_elem = soup.select_one('.ltx_abstract')
        if abstract_elem:
            # 移除标题
            for h2 in abstract_elem.find_all('h2'):
                h2.decompose()
            return self._clean_text(abstract_elem.get_text())

        # 备用选择器
        abstract_elem = soup.select_one('blockquote.abstract')
        if abstract_elem:
            text = abstract_elem.get_text()
            # 移除 "Abstract" 前缀
            text = re.sub(r'^Abstract\s*', '', text, flags=re.IGNORECASE)
            return self._clean_text(text)

        return ''

    def _convert_body(self, soup: BeautifulSoup) -> str:
        """转换正文内容"""
        # 找到正文容器
        content = soup.select_one('.ltx_page_content')
        if not content:
            content = soup.select_one('.ltx_document')
        if not content:
            content = soup.body

        if not content:
            return ''

        # 移除不需要的元素
        for tag in content.find_all(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        # 移除摘要部分（已单独处理）
        for abstract in content.find_all(class_='ltx_abstract'):
            abstract.decompose()

        # 移除标题和作者部分（已单独处理）
        for title in content.find_all(class_='ltx_title_document'):
            title.decompose()
        for authors in content.find_all(class_='ltx_authors'):
            authors.decompose()

        # 转换为 Markdown
        markdown = self._html_to_markdown(content)

        return markdown

    def _html_to_markdown(self, element) -> str:
        """将 HTML 元素转换为 Markdown"""
        if isinstance(element, NavigableString):
            text = str(element)
            # 清理多余空白但保留必要格式
            return text

        if element.name is None:
            return ''.join(self._html_to_markdown(child) for child in element.children)

        # 处理不同的 HTML 标签
        tag = element.name
        children_text = ''.join(self._html_to_markdown(child) for child in element.children)

        # 标题
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag[1])
            # 清理标题文本
            clean_text = self._clean_text(children_text)
            if clean_text:
                return f"\n\n{'#' * level} {clean_text}\n\n"
            return ''

        # 段落
        if tag == 'p':
            clean_text = self._clean_text(children_text)
            if clean_text:
                return f"\n\n{clean_text}\n\n"
            return ''

        # 数学公式
        if tag == 'math' or 'ltx_math' in element.get('class', []):
            return self._convert_math(element)

        # 行内公式
        if tag == 'span' and 'ltx_math' in element.get('class', []):
            return self._convert_math(element, inline=True)

        # 列表
        if tag == 'ul':
            items = []
            for li in element.find_all('li', recursive=False):
                item_text = self._clean_text(self._html_to_markdown(li))
                if item_text:
                    items.append(f"- {item_text}")
            return '\n' + '\n'.join(items) + '\n'

        if tag == 'ol':
            items = []
            for i, li in enumerate(element.find_all('li', recursive=False), 1):
                item_text = self._clean_text(self._html_to_markdown(li))
                if item_text:
                    items.append(f"{i}. {item_text}")
            return '\n' + '\n'.join(items) + '\n'

        # 引用
        if tag == 'blockquote':
            lines = children_text.strip().split('\n')
            return '\n' + '\n'.join(f"> {line}" for line in lines if line.strip()) + '\n'

        # 代码块
        if tag == 'pre':
            code = element.find('code')
            code_text = code.get_text() if code else children_text
            return f"\n\n```\n{code_text}\n```\n\n"

        if tag == 'code':
            # 行内代码
            if element.parent and element.parent.name == 'pre':
                return children_text
            return f"`{children_text}`"

        # 链接
        if tag == 'a':
            href = element.get('href', '')
            return f"[{children_text}]({href})"

        # 图片
        if tag == 'img':
            src = element.get('src', '')
            alt = element.get('alt', 'image')
            return f"![{alt}]({src})"

        # 强调
        if tag in ['strong', 'b']:
            return f"**{children_text}**"

        if tag in ['em', 'i']:
            return f"*{children_text}*"

        # 表格
        if tag == 'table':
            return self._convert_table(element)

        # 换行
        if tag == 'br':
            return '\n'

        # 分隔线
        if tag == 'hr':
            return '\n\n---\n\n'

        # div 和 section 递归处理
        if tag in ['div', 'section', 'article', 'main', 'span']:
            return children_text

        # 默认返回子元素内容
        return children_text

    def _convert_math(self, element, inline: bool = False) -> str:
        """转换数学公式"""
        # 尝试获取 LaTeX 源码
        latex = element.get('alttext', '')

        if not latex:
            # 尝试从 annotation 获取
            annotation = element.find('annotation')
            if annotation and annotation.get('encoding') == 'application/x-tex':
                latex = annotation.get_text()

        if not latex:
            # 尝试从 mathvariant 属性推断
            latex = self._extract_latex_from_mathml(element)

        if latex:
            if inline:
                return f"${latex}$"
            return f"\n\n$$\n{latex}\n$$\n\n"

        # 无法提取 LaTeX，使用纯文本
        text = element.get_text().strip()
        if text:
            if inline:
                return f"${text}$"
            return f"\n\n$$\n{text}\n$$\n\n"

        return ''

    def _extract_latex_from_mathml(self, element) -> str:
        """从 MathML 提取 LaTeX（简化版本）"""
        # 这是一个简化的实现，处理常见的数学符号
        text = element.get_text()

        # 常见符号映射
        symbol_map = {
            'α': r'\alpha',
            'β': r'\beta',
            'γ': r'\gamma',
            'δ': r'\delta',
            'ε': r'\epsilon',
            'θ': r'\theta',
            'λ': r'\lambda',
            'μ': r'\mu',
            'π': r'\pi',
            'σ': r'\sigma',
            'φ': r'\phi',
            'ω': r'\omega',
            'Ω': r'\Omega',
            'Σ': r'\Sigma',
            'Π': r'\Pi',
            '∞': r'\infty',
            '∑': r'\sum',
            '∏': r'\prod',
            '∫': r'\int',
            '∂': r'\partial',
            '∇': r'\nabla',
            '≤': r'\leq',
            '≥': r'\geq',
            '≠': r'\neq',
            '≈': r'\approx',
            '×': r'\times',
            '÷': r'\div',
            '±': r'\pm',
            '→': r'\rightarrow',
            '←': r'\leftarrow',
            '↔': r'\leftrightarrow',
            '⇒': r'\Rightarrow',
            '⇐': r'\Leftarrow',
            '∈': r'\in',
            '∉': r'\notin',
            '⊂': r'\subset',
            '⊃': r'\supset',
            '∪': r'\cup',
            '∩': r'\cap',
            '∅': r'\emptyset',
            'ℝ': r'\mathbb{R}',
            'ℕ': r'\mathbb{N}',
            'ℤ': r'\mathbb{Z}',
            'ℚ': r'\mathbb{Q}',
            'ℂ': r'\mathbb{C}',
        }

        for symbol, latex in symbol_map.items():
            text = text.replace(symbol, latex)

        return text

    def _convert_table(self, table) -> str:
        """转换表格"""
        rows = []
        header_row = None

        # 处理表头
        thead = table.find('thead')
        if thead:
            headers = [th.get_text().strip() for th in thead.find_all(['th', 'td'])]
            if headers:
                header_row = '| ' + ' | '.join(headers) + ' |'
                rows.append(header_row)
                rows.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')

        # 处理表体
        tbody = table.find('tbody') or table
        for tr in tbody.find_all('tr'):
            cells = [td.get_text().strip().replace('\n', ' ') for td in tr.find_all(['td', 'th'])]
            if cells:
                row = '| ' + ' | '.join(cells) + ' |'
                rows.append(row)

        if not rows:
            return ''

        # 如果没有表头，使用第一行作为表头
        if not header_row and rows:
            first_row = rows[0]
            cell_count = first_row.count('|') - 1
            rows.insert(1, '| ' + ' | '.join(['---'] * cell_count) + ' |')

        return '\n' + '\n'.join(rows) + '\n'

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text

    def _build_markdown(self, title: str, authors: str, abstract: str,
                        body: str, url: str, article_id: str) -> str:
        """构建完整的 Markdown 文档"""
        parts = []

        # 标题
        parts.append(f"# {title}\n")

        # 元信息
        parts.append(f"\n**Authors:** {authors}\n")
        parts.append(f"\n**arXiv ID:** [{article_id}]({url})\n")

        # 摘要
        if abstract:
            parts.append("\n## Abstract\n")
            parts.append(abstract)
            parts.append("\n")

        # 正文
        if body:
            parts.append("\n---\n")
            parts.append(body)

        return '\n'.join(parts)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='Convert arXiv HTML page to Markdown')
    parser.add_argument('url', help='arXiv HTML page URL (e.g., https://arxiv.org/html/2602.02276v1)')
    parser.add_argument('-o', '--output', default='.', help='Output directory (default: current directory)')
    parser.add_argument('-t', '--title', help='Custom title')
    parser.add_argument('-a', '--author', help='Custom author')

    args = parser.parse_args()

    converter = ArxivToMarkdown(output_dir=args.output)
    success, markdown, filepath = converter.convert(
        url=args.url,
        custom_title=args.title,
        custom_author=args.author
    )

    if success:
        print(f"\n[Done] File saved to: {filepath}")
    else:
        print("\n[Failed] Conversion failed")
        sys.exit(1)


if __name__ == '__main__':
    main()