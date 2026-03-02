"""
微信公众号文章转 Markdown 工具

支持：
- 通过搜狗微信搜索获取文章
- 通过 Playwright 模拟浏览器获取（应对反爬）
- 保留图片原始 URL、代码块等格式
- 登录获取 Cookie（通过 Playwright 模拟登录微信）
"""

import os
import re
import sys
import json
import time
import hashlib
import argparse
from pathlib import Path
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

# Windows 编码修复
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 默认 Cookie 文件路径
DEFAULT_COOKIE_FILE = Path(__file__).parent.parent.parent / "config" / "wechat_cookies.json"


class WeChatAuth:
    """微信登录认证模块"""

    def __init__(self, cookie_file: str = None):
        self.cookie_file = Path(cookie_file) if cookie_file else DEFAULT_COOKIE_FILE
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)

    def login_interactive(self, headless: bool = False) -> bool:
        """
        交互式登录，打开浏览器让用户扫码登录微信公众号

        Args:
            headless: 是否无头模式（建议为 False）

        Returns:
            是否登录成功
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[Error] Playwright not installed.")
            print("Run: pip install playwright && playwright install chromium")
            return False

        print("\n" + "=" * 50)
        print("微信公众号登录助手")
        print("=" * 50)
        print("\n即将打开浏览器，请在浏览器中扫码登录。")
        print("登录成功后，回到此终端按 Enter 键保存 Cookie。\n")
        input("按 Enter 键打开浏览器...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
                locale='zh-CN',
            )

            page = context.new_page()

            try:
                # 访问微信公众平台登录页面
                page.goto('https://mp.weixin.qq.com/', wait_until='networkidle', timeout=30000)

                print("\n[等待登录] 请在浏览器中用手机微信扫码登录...")
                print("[提示] 登录成功后，回到此终端按 Enter 键保存 Cookie")

                # 等待用户在终端按回车确认登录完成
                input("\n登录完成后，按 Enter 键保存 Cookie...")

                # 获取 cookies
                cookies = context.cookies()

                wechat_cookies = {}
                for cookie in cookies:
                    domain = cookie.get('domain', '')
                    if 'weixin.qq.com' in domain or 'mp.weixin' in domain:
                        wechat_cookies[cookie['name']] = cookie['value']

                if wechat_cookies:
                    self.save_cookies(wechat_cookies)
                    print("\n" + "=" * 50)
                    print("[成功] Cookie 已保存")
                    print(f"[信息] Cookie 文件: {self.cookie_file}")
                    print("=" * 50 + "\n")
                    return True
                else:
                    print("\n[警告] 未获取到有效 Cookie，请确认已登录")
                    return False

            except Exception as e:
                print(f"\n[错误] 登录过程出错: {e}")
                return False
            finally:
                browser.close()

    def save_cookies(self, cookies: dict):
        """保存 cookies 到文件"""
        with open(self.cookie_file, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)

    def load_cookies(self) -> Optional[dict]:
        """从文件加载 cookies"""
        if not self.cookie_file.exists():
            return None

        try:
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Warning] Failed to load cookies: {e}")
            return None

    def set_cookie_from_string(self, cookie_str: str) -> dict:
        """从字符串解析 cookie"""
        cookies = {}
        if not cookie_str:
            return cookies

        for item in cookie_str.split(';'):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=', 1)
                cookies[key.strip()] = value.strip()

        return cookies

    def check_login_status(self) -> bool:
        """检查当前 Cookie 是否有效"""
        cookies = self.load_cookies()
        if not cookies:
            return False

        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            })
            session.cookies.update(cookies)

            # 尝试访问微信网页
            resp = session.get('https://web.wechat.com/', timeout=10, allow_redirects=False)

            if resp.status_code in [200, 302]:
                return True
        except Exception:
            pass

        return False


class WeChatClient:
    """微信客户端，处理文章获取"""

    def __init__(self, cookies: Optional[dict] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://weixin.sogou.com/',
        })

        if cookies:
            self.session.cookies.update(cookies)

    def extract_article_id(self, url: str) -> Optional[str]:
        """从 URL 中提取文章信息"""
        # 匹配微信文章链接
        # 格式: https://mp.weixin.qq.com/s/xxx 或 https://mp.weixin.qq.com/s?src=xxx
        if 'mp.weixin.qq.com' in url:
            # 检查是否是文章链接
            if '/s/' in url or '/s?' in url:
                return url
        return None

    def search_article(self, keyword: str) -> Optional[str]:
        """通过搜狗微信搜索文章"""
        try:
            search_url = f"https://weixin.sogou.com/weixin?type=2&query={keyword}"
            print(f"[Search] Searching: {keyword}")

            resp = self.session.get(search_url, timeout=30)
            resp.encoding = 'utf-8'

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 查找搜索结果中的第一条文章链接
            result = soup.select_one('div.txt-box h3 a')
            if result:
                href = result.get('href')
                if href:
                    if href.startswith('/'):
                        href = 'https://weixin.sogou.com' + href
                    print(f"[Search] Found article: {href}")
                    return href

            print("[Search] No results found")
            return None
        except Exception as e:
            print(f"[Search] Error: {e}")
            return None

    def fetch_via_browser(self, url: str) -> Optional[str]:
        """使用 Playwright 模拟浏览器获取"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[Error] Playwright not installed.")
            print("Run: pip install playwright && playwright install chromium")
            return None

        print(f"[Browser] Launching browser for: {url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
            )

            # 注入 cookies
            if self.session.cookies:
                cookies = []
                for name, value in self.session.cookies.items():
                    cookies.append({
                        'name': name,
                        'value': value,
                        'domain': '.weixin.qq.com',
                        'path': '/'
                    })
                if cookies:
                    context.add_cookies(cookies)

            page = context.new_page()

            try:
                page.goto(url, wait_until='networkidle', timeout=60000)

                # 等待内容加载
                page.wait_for_selector('#js_content, .rich_media_content', timeout=15000)

                # 滚动页面触发懒加载
                for _ in range(3):
                    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    time.sleep(0.5)

                # 获取页面内容
                html = page.content()
                return html

            except Exception as e:
                print(f"[Browser] Error: {e}")
                return None
            finally:
                browser.close()


import os
import re
import json
import time
from pathlib import Path
from typing import Optional, Tuple
import requests
from bs4 import BeautifulSoup


class WeChatToMarkdown:
    """
    针对数学公式优化的微信文章转 Markdown 工具

    核心逻辑：
    1. 优先提取 data-formula 属性，直接替换原节点，切断乱码污染源。
    2. 处理微信特有的 SVG 占位符和零宽空格。
    3. 支持本地图片下载与相对路径引用。
    4. 将数学公式 SVG 渲染为 PNG 图片保存。
    """

    def __init__(self, output_dir: str = ".", cookies: Optional[dict] = None, download_images: bool = True):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_images = download_images
        self.image_dir = None
        self.image_count = 0
        self.formula_count = 0
        self.article_prefix = ""
        self._svg_converter = None
        # 这里的 client 使用你之前定义的 WeChatClient
        from __main__ import WeChatClient
        self.client = WeChatClient(cookies=cookies)

    def _get_svg_converter(self):
        """延迟加载 SVG 转换器"""
        if self._svg_converter is None:
            try:
                import cairosvg
                self._svg_converter = 'cairosvg'
            except ImportError:
                try:
                    from svglib.svglib import svg2rlg
                    from reportlab.graphics import renderPM
                    self._svg_converter = 'svglib'
                except ImportError:
                    print("[Warning] Neither cairosvg nor svglib installed. Math formulas will be skipped.")
                    print("[Warning] Install with: pip install cairosvg OR pip install svglib reportlab")
                    self._svg_converter = None
        return self._svg_converter

    def _svg_to_png(self, svg_content: str, save_path: Path) -> bool:
        """将 SVG 内容转换为 PNG 图片"""
        converter = self._get_svg_converter()
        if not converter:
            return False

        try:
            # 确保 SVG 有正确的尺寸
            # 微信 SVG 通常有 viewBox，但可能缺少明确的 width/height
            if 'viewBox=' in svg_content and ('width=' not in svg_content or 'height=' not in svg_content):
                # 从 viewBox 提取尺寸
                match = re.search(r'viewBox="([\d.\-\s]+)"', svg_content)
                if match:
                    values = match.group(1).split()
                    if len(values) == 4:
                        width = float(values[2]) - float(values[0])
                        height = float(values[3]) - float(values[1])
                        # 缩放到合适大小 (基于 ex 单位，通常 1ex ≈ 8px，放大到 2x 以提高清晰度)
                        scale = 2.0
                        width_px = int(width * scale)
                        height_px = int(height * scale)
                        # 插入 width 和 height 属性
                        svg_content = svg_content.replace('<svg', f'<svg width="{width_px}" height="{height_px}"', 1)

            if converter == 'cairosvg':
                import cairosvg
                cairosvg.svg2png(bytestring=svg_content.encode('utf-8'), write_to=str(save_path),
                                  scale=2)  # 2x scale for better quality
            else:  # svglib
                from svglib.svglib import svg2rlg
                from reportlab.graphics import renderPM
                from io import BytesIO
                drawing = svg2rlg(BytesIO(svg_content.encode('utf-8')))
                if drawing:
                    renderPM.drawToFile(drawing, str(save_path), 'PNG')
                else:
                    return False
            return True
        except Exception as e:
            print(f"[Warning] Failed to convert SVG to PNG: {e}")
            return False

    def _download_image(self, url: str, save_path: Path) -> bool:
        """下载图片并保持 Referer 以绕过防盗链"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://mp.weixin.qq.com/',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            }
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(resp.content)
                return True
        except Exception as e:
            print(f"[Warning] Failed to download image: {e}")
        return False

    def _process_image_url(self, url: str) -> str:
        """处理图片链接并生成本地存储路径"""
        if not self.download_images or not url:
            return url
        if url.startswith('//'):
            url = 'https:' + url

        if not self.image_dir:
            # 统一放在 output_dir/database/images 目录下
            self.image_dir = self.output_dir / 'database' / 'images'
            self.image_dir.mkdir(parents=True, exist_ok=True)

        # 识别格式
        ext = '.jpg'
        if 'wx_fmt=png' in url or url.endswith('.png'):
            ext = '.png'
        elif 'wx_fmt=gif' in url or url.endswith('.gif'):
            ext = '.gif'
        elif 'wx_fmt=webp' in url or url.endswith('.webp'):
            ext = '.webp'

        self.image_count += 1
        filename = f"{self.article_prefix}_img_{self.image_count:03d}{ext}" if self.article_prefix else f"img_{self.image_count:03d}{ext}"
        save_path = self.image_dir / filename

        if self._download_image(url, save_path):
            return f"images/{filename}"
        return url

    def _process_svg_formulas(self, soup):
        """
        处理微信文章中的 SVG 数学公式

        微信使用 SVG 来渲染数学公式，通常结构为:
        <span>&nbsp;</span>  <- 占位符
        <span><svg>...</svg></span>  <- 实际公式

        SVG 中包含 aria-label 或 aria-describedby 可能有公式描述
        """
        # 确保 image_dir 存在
        if not self.image_dir:
            self.image_dir = self.output_dir / 'database' / 'images'
            self.image_dir.mkdir(parents=True, exist_ok=True)

        # 查找所有包含数学内容的 SVG
        # 微信数学公式 SVG 通常有 role="img" 和 aria-label="插图" 或类似属性
        for svg in soup.find_all('svg'):
            # 检查是否是数学公式 SVG
            # 特征: role="img", 有 viewBox, 包含 data-mml-node 属性的子元素
            is_math_svg = False

            # 检查是否有数学相关属性
            if svg.get('role') == 'img':
                # 检查内部是否有 data-mml-node 属性 (MathJax 生成的标志)
                if svg.find(attrs={'data-mml-node': True}):
                    is_math_svg = True

            if not is_math_svg:
                continue

            # 找到 SVG 所在的 span 容器
            parent_span = svg.find_parent('span')
            if not parent_span:
                parent_span = svg.parent

            # 查找前面的 &nbsp; 占位 span (通常紧跟在公式前)
            prev_sibling = parent_span.find_previous_sibling() if parent_span else None
            nbsp_span = None

            # 检查前一个兄弟是否是只包含 &nbsp; 的 span
            if prev_sibling and prev_sibling.name == 'span':
                text = prev_sibling.get_text()
                if text.strip() == '' or text == '\xa0' or text == '&nbsp;' or text == ' ':
                    nbsp_span = prev_sibling

            # 将 SVG 转换为 PNG 图片
            svg_content = str(svg)
            self.formula_count += 1
            filename = f"{self.article_prefix}_formula_{self.formula_count:03d}.png" if self.article_prefix else f"formula_{self.formula_count:03d}.png"
            save_path = self.image_dir / filename

            if self._svg_to_png(svg_content, save_path):
                # 创建替换内容 - 使用图片引用
                replacement = f'![]({filename})'

                # 移除占位 span
                if nbsp_span:
                    nbsp_span.decompose()

                # 替换整个父 span (包含 SVG 的那个)
                parent_span.replace_with(replacement)
            else:
                # 转换失败，保留原始内容或使用占位符
                # 尝试从 aria-label 获取一些信息
                aria_label = svg.get('aria-label', '')
                if aria_label and aria_label != '插图':
                    parent_span.replace_with(f'[{aria_label}]')
                else:
                    # 删除 SVG 以避免乱码
                    svg.decompose()

    def _process_wechat_elements(self, soup):
        """核心修复：在转换为文本前，手术式清除公式节点的干扰"""

        # 0. 先处理 SVG 数学公式（在处理 data-formula 之前）
        self._process_svg_formulas(soup)

        # 1. 提取所有带 data-formula 的标签（无论它是 span, section 还是 svg）
        for formula_node in soup.find_all(attrs={"data-formula": True}):
            latex = formula_node.get('data-formula')
            if not latex:
                continue

            # 清理 latex 中可能的 HTML 实体
            latex = latex.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

            f_type = formula_node.get('data-formula-type', '0')

            if f_type == '1':  # 块级公式
                replacement = f'\n\n$$\n{latex}\n$$\n\n'
            else:  # 行内公式，前后加空格防止与汉字粘连导致不渲染
                replacement = f' ${latex}$ '

            # 【关键】replace_with 会把该节点及其子节点（SVG, 占位符等）全部从 DOM 树中移除
            # 替换为我们干净的 LaTeX 文本
            formula_node.replace_with(replacement)

        # 2. 处理图片和表情
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('data-original') or img.get('src')
            if src:
                if 'emoji' in img.get('class', []) or 'biaoqing' in src:
                    alt = img.get('alt', '')
                    img.replace_with(alt if alt else "")
                else:
                    local_path = self._process_image_url(src)
                    img.replace_with(f'![]({local_path})')

        # 3. 处理代码块
        for pre in soup.find_all('pre'):
            code = pre.find('code')
            code_text = code.get_text() if code else pre.get_text()
            lang = ""
            if code and code.get('class'):
                # 提取 language-python 这种类名
                lang_match = re.search(r'language-(\w+)', ' '.join(code.get('class')))
                if lang_match:
                    lang = lang_match.group(1)
            pre.replace_with(f'\n```{lang}\n{code_text.strip()}\n```\n')

    def _convert_node(self, node) -> str:
        """递归转换 DOM 节点为 Markdown，清理不可见干扰字符"""
        if isinstance(node, str):
            # 微信中充斥着零宽空格 (\u200b) 和不间断空格 (\xa0)，必须清除
            return node.replace('\u200b', '').replace('\xa0', ' ')

        if node.name is None:
            return node.get_text()

        tag = node.name.lower()

        # 标题处理
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag[1])
            return f"\n{'#' * level} {node.get_text().strip()}\n\n"

        # 分段与换行
        elif tag == 'p':
            return f"{self._convert_children(node)}\n\n"
        elif tag == 'br':
            return '\n'
        elif tag == 'hr':
            return '\n---\n\n'

        # 文本格式
        elif tag in ['strong', 'b']:
            return f' **{self._convert_children(node).strip()}** '
        elif tag in ['em', 'i']:
            return f' *{self._convert_children(node).strip()}* '
        elif tag == 'code' and (not node.parent or node.parent.name != 'pre'):
            return f' `{node.get_text()}` '

        # 列表
        elif tag in ['ul', 'ol']:
            items = []
            for i, li in enumerate(node.find_all('li', recursive=False)):
                text = self._convert_children(li).strip()
                if not text: continue
                prefix = f'{i + 1}. ' if tag == 'ol' else '- '
                items.append(f'{prefix}{text}')
            return '\n' + '\n'.join(items) + '\n\n'

        # 表格
        elif tag == 'table':
            rows = []
            for tr in table.find_all('tr'):
                cells = [cell.get_text().strip() for cell in tr.find_all(['th', 'td'])]
                if cells: rows.append(cells)
            if not rows: return ''
            header = '| ' + ' | '.join(rows[0]) + ' |'
            sep = '| ' + ' | '.join(['---'] * len(rows[0])) + ' |'
            body = '\n'.join('| ' + ' | '.join(row + [''] * (len(rows[0]) - len(row))) + ' |' for row in rows[1:])
            return f'\n{header}\n{sep}\n{body}\n\n'

        # 拦截已被处理的 SVG（避免输出路径数据）
        elif tag == 'svg':
            return ''

        # 穿透容器标签
        elif tag in ['div', 'span', 'section', 'article', 'figure']:
            return self._convert_children(node)

        else:
            return self._convert_children(node)

    def _convert_children(self, node) -> str:
        return ''.join(self._convert_node(child) for child in node.children)

    def html_to_markdown(self, html: str, title: str = None) -> str:
        """将微信 HTML 内容转换为干净的 Markdown"""
        soup = BeautifulSoup(html, 'html.parser')

        # 清除脚本和样式
        for unwanted in soup.find_all(['script', 'style', 'noscript', 'iframe']):
            unwanted.decompose()

        # 预处理公式和图片
        self._process_wechat_elements(soup)

        # 执行递归解析
        md = self._convert_node(soup)

        # 最终清洗：压缩连续空行
        md = re.sub(r'\n{3,}', '\n\n', md)

        if title:
            md = f"# {title}\n\n{md.strip()}"
        return md

    def convert(self, url: str, use_browser: bool = True) -> Optional[Tuple[str, str]]:
        """主入口"""
        if url.startswith('http'):
            article_url = url
        else:
            article_url = self.client.search_article(url)
            if not article_url: return None

        # 通过浏览器模拟获取完整 HTML
        html = self.client.fetch_via_browser(article_url)
        if not html:
            print("[Error] Failed to fetch HTML via browser.")
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # 获取标题并建立安全文件名
        title_tag = soup.find('h1', id='activity-name') or soup.find('h1', class_='rich_media_title')
        title = title_tag.get_text().strip() if title_tag else "wechat_article"
        self.article_prefix = re.sub(r'[<>:"/\\|?*]', '_', title)[:50]
        self.image_count = 0
        self.formula_count = 0

        # 微信文章主体内容通常在 js_content 中
        content_div = soup.find('div', id='js_content')
        if not content_div:
            print("[Error] Could not find article body.")
            return None

        markdown_body = self.html_to_markdown(str(content_div), title)

        # 拼接 YAML 元数据
        full_md = f"---\ntitle: {title}\nsource: {article_url}\ndate: {time.strftime('%Y-%m-%d')}\n---\n\n{markdown_body}"

        # 保存
        output_path = self.output_dir / 'database' / f"{self.article_prefix}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_md)

        print(f"[Success] Markdown saved to: {output_path}")
        return full_md, str(output_path)

def cmd_login(args):
    """登录命令"""
    auth = WeChatAuth(cookie_file=args.cookie_file)

    if args.check:
        if auth.check_login_status():
            print("[状态] 已登录，Cookie 有效")
        else:
            print("[状态] 未登录或 Cookie 已过期")
        return

    # 如果提供了 cookie 字符串
    if args.cookie:
        cookies = auth.set_cookie_from_string(args.cookie)
        if cookies:
            auth.save_cookies(cookies)
            print(f"[成功] Cookie 已保存到: {auth.cookie_file}")
        return

    # 交互式登录
    success = auth.login_interactive(headless=False)
    if not success:
        sys.exit(1)


def cmd_fetch(args):
    """爬取命令"""
    # 加载 cookies
    cookies = None
    cookie_file = args.cookie_file or str(DEFAULT_COOKIE_FILE)

    if Path(cookie_file).exists():
        auth = WeChatAuth(cookie_file=cookie_file)
        cookies = auth.load_cookies()
        if cookies:
            print(f"[信息] 已加载 Cookie: {cookie_file}")

    # 如果命令行指定了 cookie 字符串，优先使用
    if args.cookie:
        auth = WeChatAuth()
        cookies = auth.set_cookie_from_string(args.cookie)

    converter = WeChatToMarkdown(
        output_dir=args.output,
        cookies=cookies
    )

    result = converter.convert(args.url, use_browser=args.browser)

    if not result:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='微信公众号文章转 Markdown 工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 登录（可选，用于需要认证的文章）
  python wechat2markdown.py login -c "cookie字符串"

  # 爬取文章（直接使用 URL）
  python wechat2markdown.py fetch "https://mp.weixin.qq.com/s/xxx"

  # 爬取文章（使用搜索关键词）
  python wechat2markdown.py fetch "Python 教程"

  # 指定输出目录
  python wechat2markdown.py fetch "https://mp.weixin.qq.com/s/xxx" -o ./output
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # login 子命令
    login_parser = subparsers.add_parser('login', help='登录微信获取 Cookie')
    login_parser.add_argument('-c', '--cookie', help='从浏览器复制的 Cookie 字符串')
    login_parser.add_argument('-f', '--cookie-file', help='Cookie 保存路径')
    login_parser.add_argument('--check', action='store_true', help='检查登录状态')
    login_parser.set_defaults(func=cmd_login)

    # fetch 子命令
    fetch_parser = subparsers.add_parser('fetch', help='爬取微信文章')
    fetch_parser.add_argument('url', help='微信文章 URL 或搜索关键词')
    fetch_parser.add_argument('-o', '--output', default='.', help='输出目录 (默认当前目录)')
    fetch_parser.add_argument('--browser', action='store_true', default=True, help='使用浏览器模式 (默认开启)')
    fetch_parser.add_argument('-c', '--cookie', help='Cookie 字符串')
    fetch_parser.add_argument('-f', '--cookie-file', help='Cookie 文件路径')
    fetch_parser.set_defaults(func=cmd_fetch)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == '__main__':
    main()