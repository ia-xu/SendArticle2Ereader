"""
知乎专栏文章转 Markdown 工具

支持：
- 通过 API 直接获取文章内容（推荐）
- 通过 Playwright 模拟浏览器获取（应对反爬）
- 自动下载图片并替换链接
- 保留代码块、公式等格式
- 登录获取 Cookie（通过 Playwright 模拟登录）
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

# Windows 编码修复
if sys.platform == 'win32':
    import codecs
    # 只在直接运行时修复编码，避免在 Flask 等环境中出错
    if hasattr(sys.stdout, 'buffer') and not isinstance(sys.stdout, codecs.StreamWriter):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    if hasattr(sys.stderr, 'buffer') and not isinstance(sys.stderr, codecs.StreamWriter):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 默认 Cookie 文件路径
DEFAULT_COOKIE_FILE = Path(__file__).parent.parent.parent / "config" / "zhihu_cookies.json"


class ZhihuAuth:
    """知乎登录认证模块"""

    def __init__(self, cookie_file: str = None):
        self.cookie_file = Path(cookie_file) if cookie_file else DEFAULT_COOKIE_FILE
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)

    def login_interactive(self, headless: bool = False) -> bool:
        """
        交互式登录，打开浏览器让用户手动登录

        Args:
            headless: 是否无头模式（登录时建议为 False，方便用户操作）

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
        print("知乎登录助手")
        print("=" * 50)
        print("\n即将打开浏览器，请在浏览器中完成登录操作。")
        print("登录成功后，页面会自动跳转，届时 Cookie 将自动保存。\n")
        print("提示：")
        print("  - 可以使用扫码登录或账号密码登录")
        print("  - 登录成功后请等待页面跳转到首页")
        print("  - 看到 '登录成功' 提示后即可关闭\n")
        input("按 Enter 键继续...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
                locale='zh-CN',
            )

            page = context.new_page()

            try:
                # 访问知乎登录页
                page.goto('https://www.zhihu.com/signin', wait_until='networkidle')

                print("\n[等待登录] 请在浏览器中完成登录...")

                # 等待登录成功（检测页面跳转到首页或个人主页）
                # 登录成功后会跳转到 www.zhihu.com 或显示用户头像
                max_wait = 300  # 最长等待 5 分钟
                start_time = time.time()

                while time.time() - start_time < max_wait:
                    current_url = page.url

                    # 检查是否已登录（URL 不再是登录页）
                    if 'signin' not in current_url and 'login' not in current_url:
                        # 额外检查：页面是否有用户头像等登录后才有的元素
                        try:
                            # 检查是否存在用户相关元素
                            user_menu = page.query_selector('.AppHeader-profile, .UserLink, [aria-label="用户菜单"]')
                            if user_menu or page.url == 'https://www.zhihu.com/' or 'www.zhihu.com' in current_url:
                                time.sleep(2)  # 等待页面完全加载

                                # 获取 cookies
                                cookies = context.cookies()

                                # 筛选知乎相关的 cookies
                                zhihu_cookies = {}
                                for cookie in cookies:
                                    if 'zhihu.com' in cookie.get('domain', ''):
                                        zhihu_cookies[cookie['name']] = cookie['value']

                                # 检查关键 cookie
                                if 'z_c0' in zhihu_cookies or '_xsrf' in zhihu_cookies:
                                    # 保存 cookies
                                    self.save_cookies(zhihu_cookies)

                                    print("\n" + "=" * 50)
                                    print("[成功] 登录成功！Cookie 已保存")
                                    print(f"[信息] Cookie 文件: {self.cookie_file}")
                                    print("=" * 50 + "\n")
                                    return True

                        except Exception:
                            pass

                    time.sleep(1)

                print("\n[超时] 登录等待超时，请重试")
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

            # 请求用户信息接口
            resp = session.get('https://www.zhihu.com/api/v4/me', timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                if data.get('uid'):
                    print(f"[信息] 当前登录用户: {data.get('name', 'Unknown')}")
                    return True
        except Exception:
            pass

        return False


class ZhihuClient:
    """知乎客户端，处理 API 请求和反爬"""

    def __init__(self, cookies: Optional[dict] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Origin': 'https://www.zhihu.com',
            'Referer': 'https://www.zhihu.com/',
        })

        if cookies:
            self.session.cookies.update(cookies)

    def extract_article_id(self, url: str) -> Optional[str]:
        """从 URL 中提取文章 ID"""
        # 匹配 https://zhuanlan.zhihu.com/p/123456789
        match = re.search(r'zhuanlan\.zhihu\.com/p/(\d+)', url)
        if match:
            return match.group(1)

        # 匹配 https://www.zhihu.com/question/xxx/answer/yyy
        match = re.search(r'zhihu\.com/question/\d+/answer/(\d+)', url)
        if match:
            return f"answer_{match.group(1)}"

        # 匹配 https://zhuanlan.zhihu.com/p/xxx （短链接）
        match = re.search(r'zhihu\.com/p/(\d+)', url)
        if match:
            return match.group(1)

        return None

    def fetch_via_api(self, article_id: str) -> Optional[dict]:
        """通过 API 获取文章内容"""
        # 如果是 answer 类型
        if article_id.startswith('answer_'):
            answer_id = article_id.replace('answer_', '')
            api_url = f"https://www.zhihu.com/api/v4/answers/{answer_id}"
            params = {'include': 'content,author,question'}
        else:
            api_url = f"https://www.zhihu.com/api/v4/articles/{article_id}"

        try:
            print(f"[API] Fetching: {api_url}")
            resp = self.session.get(api_url, timeout=30)

            if resp.status_code == 401:
                print("[API] 401 Unauthorized - 需要登录或 cookie 已过期")
                return None

            if resp.status_code == 404:
                print("[API] 404 Not Found - 文章不存在或已删除")
                return None

            if resp.status_code == 403:
                print("[API] 403 Forbidden - 被反爬拦截，尝试使用浏览器模式")
                return None

            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"[API] Request failed: {e}")
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
                        'domain': '.zhihu.com',
                        'path': '/'
                    })
                if cookies:
                    context.add_cookies(cookies)

            page = context.new_page()

            try:
                page.goto(url, wait_until='networkidle', timeout=60000)

                # 等待内容加载
                page.wait_for_selector('.Post-RichText, .RichText, .RichContent-inner', timeout=15000)

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


class ZhihuToMarkdown:
    """知乎文章转 Markdown"""

    def __init__(self, output_dir: str = ".", cookies: Optional[dict] = None, file_prefix: str = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.file_prefix = file_prefix  # 可选的文件前缀（用于 file_id）

        self.client = ZhihuClient(cookies=cookies)

    def html_to_markdown(self, html: str, title: str = None) -> str:
        """将 HTML 转换为 Markdown"""
        soup = BeautifulSoup(html, 'html.parser')

        # 清理不需要的标签
        for tag in soup.find_all(['script', 'style', 'noscript', 'iframe']):
            tag.decompose()

        # 处理知乎特有的元素
        self._process_zhihu_elements(soup)

        # 转换为 Markdown
        md = self._convert_node(soup)

        # 清理多余空行
        md = re.sub(r'\n{3,}', '\n\n', md)
        md = md.strip()

        # 添加标题
        if title:
            md = f"# {title}\n\n{md}"

        return md

    def _is_inline_formula(self, img) -> bool:
        """
        判断公式图片是否为行内公式

        知乎公式图片的 HTML 结构：
        - 行内公式: 通常在 <span> 或 <p> 内，前后有文字
        - 块级公式: 通常在独立的 <div> 或 <figure> 中，独占一行
        """
        # 1. 检查 img 标签自身的 class
        img_class = ' '.join(img.get('class', []))
        if 'ee' in img_class:
            return True

        # 2. 检查父元素
        parent = img.find_parent()

        # 如果在典型行内元素中，是行内公式
        if parent and parent.name in ['span', 'em', 'strong', 'a']:
            return True

        # 3. 关键判断：检查公式所在的直接父元素是否还有其他内容
        # 获取父元素的直接内容（不包括子标签的文字）
        direct_parent = img.parent
        if direct_parent:
            # 检查父元素中公式图片前后是否有其他内容
            # 获取父元素的所有子节点
            children = list(direct_parent.children)

            # 如果只有一个子节点（即这个图片），则是块级公式
            if len(children) == 1:
                return False

            # 如果有多个子节点，检查是否有文字内容
            for child in children:
                if isinstance(child, str):
                    # 文本节点，检查是否有非空白内容
                    if child.strip():
                        return True
                elif hasattr(child, 'name'):
                    # 元素节点，检查是否是其他内容
                    if child != img:
                        # 如果是文字标签，说明是行内公式
                        if child.name in ['span', 'em', 'strong', 'a', '#text']:
                            return True
                        # 如果有文字内容
                        if child.get_text().strip():
                            return True

        # 4. 默认为块级公式
        return False

    def _process_zhihu_elements(self, soup):
        """处理知乎特有的元素"""
        # 处理 LaTeX 公式 - 知乎的公式图片（zhihu.com/equation?tex=...）
        for img in soup.find_all('img'):
            src = img.get('data-original') or img.get('data-src') or img.get('src', '')
            if 'zhihu.com/equation?tex=' in src:
                # 提取 tex 参数并 URL 解码
                match = re.search(r'equation\?tex=([^&]+)', src)
                if match:
                    latex_encoded = match.group(1)
                    # URL 解码，将 + 替换为空格
                    latex = unquote(latex_encoded.replace('+', ' '))

                    # 判断是行内公式还是块级公式
                    is_inline = self._is_inline_formula(img)

                    if is_inline:
                        # 行内公式：使用单美元符号
                        img.replace_with(f'${latex}$')
                    else:
                        # 块级公式：使用双美元符号
                        img.replace_with(f'\n$$\n{latex}\n$$\n')
                else:
                    # 无法解析，移除图片
                    img.replace_with('')
                continue  # 已处理，跳过后续的图片处理逻辑

            # 处理普通图片（保留原始 URL）
            if src and src.startswith('//'):
                src = 'https:' + src
            if src:
                img.replace_with(f'![]({src})')

        # 处理代码块
        for pre in soup.find_all('pre'):
            code = pre.find('code')
            if code:
                lang = code.get('class', [''])[0].replace('language-', '') if code.get('class') else ''
                code_text = code.get_text()
                pre.replace_with(f'\n```{lang}\n{code_text}\n```\n')
            else:
                code_text = pre.get_text()
                pre.replace_with(f'\n```\n{code_text}\n```\n')

        # 处理引用块
        for blockquote in soup.find_all('blockquote'):
            text = blockquote.get_text().strip()
            lines = text.split('\n')
            quoted = '\n'.join(f'> {line}' for line in lines)
            blockquote.replace_with(f'\n{quoted}\n')

        # 处理链接卡片
        for div in soup.find_all('div'):
            if div.get('class') and 'LinkCard' in ' '.join(div.get('class', [])):
                link = div.find('a')
                if link:
                    href = link.get('href', '')
                    text = link.get_text().strip()
                    div.replace_with(f'[{text}]({href})\n')

    def _convert_node(self, node, depth=0) -> str:
        """递归转换节点"""
        if isinstance(node, str):
            return node

        if node.name is None:
            return node.get_text()

        tag = node.name.lower()

        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag[1])
            text = node.get_text().strip()
            return f"\n{'#' * level} {text}\n\n"

        elif tag == 'p':
            text = self._convert_children(node)
            return f"{text}\n\n"

        elif tag == 'br':
            return '\n'

        elif tag == 'hr':
            return '\n---\n\n'

        elif tag in ['strong', 'b']:
            text = self._convert_children(node)
            return f'**{text}**'

        elif tag in ['em', 'i']:
            text = self._convert_children(node)
            return f'*{text}*'

        elif tag in ['code'] and node.parent and node.parent.name != 'pre':
            text = node.get_text()
            return f'`{text}`'

        elif tag == 'a':
            href = node.get('href', '')
            text = self._convert_children(node)
            if href and text:
                return f'[{text}]({href})'
            return text

        elif tag == 'img':
            src = node.get('data-original') or node.get('data-src') or node.get('src', '')
            if src and src.startswith('//'):
                src = 'https:' + src
            if src:
                return f'![]({src})\n\n'
            return ''

        elif tag in ['ul', 'ol']:
            items = []
            for i, li in enumerate(node.find_all('li', recursive=False)):
                text = self._convert_children(li).strip()
                if tag == 'ol':
                    items.append(f'{i+1}. {text}')
                else:
                    items.append(f'- {text}')
            return '\n' + '\n'.join(items) + '\n\n'

        elif tag == 'li':
            return self._convert_children(node)

        elif tag == 'blockquote':
            text = self._convert_children(node).strip()
            lines = text.split('\n')
            quoted = '\n'.join(f'> {line}' for line in lines if line.strip())
            return f'\n{quoted}\n\n'

        elif tag == 'table':
            return self._convert_table(node)

        elif tag == 'figure':
            img = node.find('img')
            if img:
                return self._convert_node(img)
            return self._convert_children(node)

        elif tag == 'noscript':
            return ''

        else:
            return self._convert_children(node)

    def _convert_children(self, node) -> str:
        """转换所有子节点"""
        parts = []
        for child in node.children:
            parts.append(self._convert_node(child))
        return ''.join(parts)

    def _convert_table(self, table) -> str:
        """转换 HTML 表格为 Markdown"""
        rows = []
        for tr in table.find_all('tr'):
            cells = []
            for cell in tr.find_all(['th', 'td']):
                text = cell.get_text().strip()
                cells.append(text)
            if cells:
                rows.append(cells)

        if not rows:
            return ''

        lines = []
        if rows:
            lines.append('| ' + ' | '.join(rows[0]) + ' |')
            lines.append('| ' + ' | '.join(['---'] * len(rows[0])) + ' |')
            for row in rows[1:]:
                while len(row) < len(rows[0]):
                    row.append('')
                lines.append('| ' + ' | '.join(row[:len(rows[0])]) + ' |')

        return '\n' + '\n'.join(lines) + '\n\n'

    def convert(self, url: str, use_browser: bool = False) -> Optional[Tuple[str, str]]:
        """
        转换知乎文章为 Markdown

        Args:
            url: 知乎文章 URL
            use_browser: 是否强制使用浏览器模式

        Returns:
            (markdown_content, output_file_path) 或 None
        """
        article_id = self.client.extract_article_id(url)
        if not article_id:
            print(f"[Error] Cannot extract article ID from URL: {url}")
            return None

        title = None
        html_content = None

        # 首先尝试 API
        if not use_browser:
            data = self.client.fetch_via_api(article_id)
            if data:
                title = data.get('title', 'Untitled')
                html_content = data.get('content') or data.get('html', '')
                author = data.get('author', {}).get('name', 'Unknown')
                print(f"[API] Article: {title} by {author}")

        # 如果 API 失败，使用浏览器
        if not html_content:
            html = self.client.fetch_via_browser(url)
            if html:
                soup = BeautifulSoup(html, 'html.parser')

                title_tag = soup.find('h1', class_='Post-Title') or soup.find('h1')
                if title_tag:
                    title = title_tag.get_text().strip()

                content_div = (
                    soup.find('div', class_='Post-RichText') or
                    soup.find('div', class_='RichText') or
                    soup.find('div', class_='RichContent-inner') or
                    soup.find('article')
                )

                if content_div:
                    html_content = str(content_div)

        if not html_content:
            print("[Error] Failed to fetch article content")
            return None

        # 转换为 Markdown
        title = title or f"zhihu_{article_id}"
        markdown = self.html_to_markdown(html_content, title)

        # 添加元信息
        meta = f"---\ntitle: {title}\nsource: {url}\n---\n\n"
        markdown = meta + markdown

        # 保存文件
        # 如果有 file_prefix，直接保存到 output_dir 根目录，文件名为 {file_prefix}.md
        # 否则保存到 output_dir/database/ 目录
        if self.file_prefix:
            output_file = self.output_dir / f"{self.file_prefix}.md"
        else:
            safe_title = re.sub(r'[<>"\\|?*]', '_', title)
            safe_title = safe_title[:50]
            output_file = self.output_dir / 'database' / f"{safe_title}.md"
            output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown)

        print(f"[Success] Saved to: {output_file}")
        return markdown, str(output_file)


def cmd_login(args):
    """登录命令"""
    auth = ZhihuAuth(cookie_file=args.cookie_file)

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
        auth = ZhihuAuth(cookie_file=cookie_file)
        cookies = auth.load_cookies()
        if cookies:
            print(f"[信息] 已加载 Cookie: {cookie_file}")

    # 如果命令行指定了 cookie 字符串，优先使用
    if args.cookie:
        auth = ZhihuAuth()
        cookies = auth.set_cookie_from_string(args.cookie)

    converter = ZhihuToMarkdown(
        output_dir=args.output,
        cookies=cookies
    )

    result = converter.convert(args.url, use_browser=args.browser)

    if not result:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='知乎专栏文章转 Markdown 工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 登录获取 Cookie（推荐先登录）
  python zhihu2markdown.py login

  # 从浏览器复制 Cookie
  python zhihu2markdown.py login -c "z_c0=xxx; _xsrf=yyy"

  # 检查登录状态
  python zhihu2markdown.py login --check

  # 爬取文章（使用已保存的 Cookie）
  python zhihu2markdown.py fetch https://zhuanlan.zhihu.com/p/123456789

  # 爬取文章（指定输出目录）
  python zhihu2markdown.py fetch https://zhuanlan.zhihu.com/p/123456789 -o ./output

  # 强制使用浏览器模式
  python zhihu2markdown.py fetch https://zhuanlan.zhihu.com/p/123456789 --browser
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # login 子命令
    login_parser = subparsers.add_parser('login', help='登录知乎获取 Cookie')
    login_parser.add_argument('-c', '--cookie', help='从浏览器复制的 Cookie 字符串')
    login_parser.add_argument('-f', '--cookie-file', help='Cookie 保存路径')
    login_parser.add_argument('--check', action='store_true', help='检查登录状态')
    login_parser.set_defaults(func=cmd_login)

    # fetch 子命令
    fetch_parser = subparsers.add_parser('fetch', help='爬取知乎文章')
    fetch_parser.add_argument('url', help='知乎文章 URL')
    fetch_parser.add_argument('-o', '--output', default='.', help='输出目录 (默认当前目录)')
    fetch_parser.add_argument('--browser', action='store_true', help='强制使用浏览器模式')
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