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
from typing import Optional, Tuple, Dict, List

import requests
from bs4 import BeautifulSoup
from tqdm.contrib.concurrent import thread_map

# Windows 编码修复
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 默认 Cookie 文件路径
DEFAULT_COOKIE_FILE = Path(__file__).parent.parent.parent / "config" / "wechat_cookies.json"

# 特殊字符映射表（用于处理 LaTeX 转义字符和非标准 Unicode 数学字母）
# 大部分数学字母符号位于 Unicode 的 Mathematical Alphanumeric Symbols 区块 (U+1D400-U+1D7FF)
SPECIAL_CHAR_MAP = {
    # 希腊字母（粗体/斜体变体）
    '1D6FD': r'\beta',
    '1D6FC': r'\alpha',
    '1D6FE': r'\gamma',
    '1D6FF': r'\delta',
    '1D700': r'\epsilon',
    '1D701': r'\zeta',
    '1D702': r'\eta',
    '1D703': r'\theta',
    '1D707': r'\kappa',
    '1D708': r'\lambda',
    '1D70F': r'\xi',
    '1D711': r'\pi',
    '1D712': r'\rho',
    '1D716': r'\sigma',
    '1D719': r'\tau',
    '1D71D': r'\phi',
    '1D71C': r'\chi',
    '1D71B': r'\psi',
    '1D71F': r'\omega',
    '1D6A8': r'\Beta',
    '1D6A9': r'\Gamma',
    '1D6AA': r'\Delta',
    '1D6AB': r'\Epsilon',
    '1D6AC': r'\Zeta',
    '1D6AD': r'\Eta',
    '1D6AE': r'\Theta',
    '1D6B2': r'\Kappa',
    '1D6B3': r'\Lambda',
    '1D6BA': r'\Xi',
    '1D6BC': r'\Pi',
    '1D6BD': r'\Rho',
    '1D6C2': r'\Sigma',
    '1D6C4': r'\Tau',
    '1D6C8': r'\Phi',
    '1D6C9': r'\Chi',
    '1D6CA': r'\Psi',
    '1D6CB': r'\Omega',
    # 数学斜体字母 (U+1D434-U+1D467 为大写，U+1D468-U+1D49B 为小写)
    '1D434': 'A', '1D435': 'B', '1D436': 'C', '1D437': 'D', '1D438': 'E',
    '1D439': 'F', '1D43A': 'G', '1D43B': 'H', '1D43C': 'I', '1D43D': 'J',
    '1D43E': 'K', '1D43F': 'L', '1D440': 'M', '1D441': 'N', '1D442': 'O',
    '1D443': 'P', '1D444': 'Q', '1D445': 'R', '1D446': 'S', '1D447': 'T',
    '1D448': 'U', '1D449': 'V', '1D44A': 'W', '1D44B': 'X', '1D44C': 'Y',
    '1D44D': 'Z',
    '1D44E': 'a', '1D44F': 'b', '1D450': 'c', '1D451': 'd', '1D452': 'e',
    '1D453': 'f', '1D454': 'g', '1D455': 'h', '1D456': 'i', '1D457': 'j',
    '1D458': 'k', '1D459': 'l', '1D45A': 'm', '1D45B': 'n', '1D45C': 'o',
    '1D45D': 'p', '1D45E': 'q', '1D45F': 'r', '1D460': 's', '1D461': 't',
    '1D462': 'u', '1D463': 'v', '1D464': 'w', '1D465': 'x', '1D466': 'y',
    '1D467': 'z',
    # 特殊数学符号
    '2212': '-',   # 减号
    '22C5': r'\cdot',  # 点乘
    '22A4': r'\top',   # 转置符号
    '2208': r'\in',    # 属于
    '2209': r'\notin', # 不属于
    '221A': r'\sqrt',  # 平方根
    '2211': r'\sum',   # 求和
    '220F': r'\prod',  # 乘积
    '222B': r'\int',   # 积分
    '2202': r'\partial', # 偏导
    '2207': r'\nabla', # 梯度
    '221E': r'\infty', # 无穷
    '2260': r'\neq',   # 不等于
    '2264': r'\leq',   # 小于等于
    '2265': r'\geq',   # 大于等于
    '2248': r'\approx', # 约等于
    '221D': r'\propto', # 正比
    # 括号
    '23B0': r'\lceil',
    '23B1': r'\rceil',
    '230A': r'\lfloor',
    '230B': r'\rfloor',
    '7C': '|',
    '2016': r'\|',
    '22BA': r'^\top',   # 常见的转置符号码点
    '2192': r'\rightarrow',
    '2190': r'\leftarrow',


}

# 需要映射为普通 ASCII 的 Unicode 数学字母（Mathematical Alphanumeric Symbols）
# 这些是将普通字母映射到其 Unicode 数学变体的表
MATH_ALPHANUMERIC_MAP = {}

# 大写斜体 A-Z (U+1D434-U+1D44D) -> A-Z
for i, code in enumerate(range(0x1D434, 0x1D44E)):
    MATH_ALPHANUMERIC_MAP[f'{code:X}'] = chr(ord('A') + i)

# 小写斜体 a-z (U+1D44E-U+1D467) -> a-z
for i, code in enumerate(range(0x1D44E, 0x1D468)):
    MATH_ALPHANUMERIC_MAP[f'{code:X}'] = chr(ord('a') + i)

# 大写粗体 A-Z (U+1D400-U+1D419) -> A-Z
for i, code in enumerate(range(0x1D400, 0x1D41A)):
    MATH_ALPHANUMERIC_MAP[f'{code:X}'] = chr(ord('A') + i)

# 小写粗体 a-z (U+1D41A-U+1D433) -> a-z
for i, code in enumerate(range(0x1D41A, 0x1D434)):
    MATH_ALPHANUMERIC_MAP[f'{code:X}'] = chr(ord('a') + i)

# 大写粗体斜体 A-Z (U+1D468-U+1D481) -> A-Z
for i, code in enumerate(range(0x1D468, 0x1D482)):
    MATH_ALPHANUMERIC_MAP[f'{code:X}'] = chr(ord('A') + i)

# 小写粗体斜体 a-z (U+1D482-U+1D49B) -> a-z
for i, code in enumerate(range(0x1D482, 0x1D49C)):
    MATH_ALPHANUMERIC_MAP[f'{code:X}'] = chr(ord('a') + i)

# 大写等宽 A-Z (U+1D670-U+1D689) -> A-Z
for i, code in enumerate(range(0x1D670, 0x1D68A)):
    MATH_ALPHANUMERIC_MAP[f'{code:X}'] = chr(ord('A') + i)

# 小写等宽 a-z (U+1D68A-U+1D6A3) -> a-z
for i, code in enumerate(range(0x1D68A, 0x1D6A4)):
    MATH_ALPHANUMERIC_MAP[f'{code:X}'] = chr(ord('a') + i)

# 希腊字母粗体/斜体变体
# 大写粗体希腊字母 (U+1D6A8-U+1D6C0 部分)
GREEK_BOLD_MAP = {
    '1D6A8': 'A', '1D6A9': 'B', '1D6AA': r'\Gamma', '1D6AB': 'E',
    '1D6AC': 'Z', '1D6AD': 'H', '1D6AE': r'\Theta', '1D6B2': 'K',
    '1D6B3': r'\Lambda', '1D6BA': r'\Xi', '1D6BC': r'\Pi', '1D6BD': 'P',
    '1D6C2': r'\Sigma', '1D6C4': 'T', '1D6C8': r'\Phi', '1D6C9': 'X',
    '1D6CA': r'\Psi', '1D6CB': r'\Omega',
}

# 小写粗体希腊字母 (U+1D6CE-U+1D6E6 部分)
GREEK_BOLD_SMALL_MAP = {
    '1D6CE': r'\alpha', '1D6CF': r'\beta', '1D6D0': r'\gamma', '1D6D1': r'\delta',
    '1D6D2': r'\epsilon', '1D6D3': r'\zeta', '1D6D4': r'\eta', '1D6D5': r'\theta',
    '1D6D9': r'\kappa', '1D6DA': r'\lambda', '1D6DF': r'\xi', '1D6E1': r'\pi',
    '1D6E2': r'\rho', '1D6E6': r'\sigma', '1D6E8': r'\tau', '1D6EC': r'\phi',
    '1D6EB': r'\chi', '1D6ED': r'\psi', '1D6EF': r'\omega',
}


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
                        'domain': '.qq.com',
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

    def __init__(self, output_dir: str = ".", cookies: Optional[dict] = None, download_images: bool = True, file_prefix: str = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_images = download_images
        self.file_prefix = file_prefix  # 可选的文件前缀（用于 file_id）
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
                lib_path = r'C:\Program Files\GTK3-Runtime Win64\bin'
                if lib_path not in os.environ['PATH']:
                    os.environ['PATH'] = lib_path + os.pathsep + os.environ.get('PATH', '')

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
        """将 SVG 内容转换为 PNG 图片（添加白色背景）"""
        converter = self._get_svg_converter()
        if not converter:
            return False

        try:
            # 解析 viewBox 参数
            viewBox_match = re.search(r'viewBox="([\d.\-\s]+)"', svg_content)
            if viewBox_match:
                values = viewBox_match.group(1).split()
                if len(values) == 4:
                    vb_x = float(values[0])  # min-x
                    vb_y = float(values[1])  # min-y
                    vb_width = float(values[2])  # width
                    vb_height = float(values[3])  # height

                    # 1. 添加白色背景矩形（使用 viewBox 的实际坐标范围）
                    # 微信 SVG 可能有负数的 y 坐标，需要正确设置背景位置
                    svg_match = re.search(r'<svg[^>]*>', svg_content)
                    if svg_match:
                        svg_start_tag = svg_match.group(0)
                        # 背景矩形覆盖整个 viewBox 区域
                        bg_rect = f'<rect x="{vb_x}" y="{vb_y}" width="{vb_width}" height="{vb_height}" fill="white"/>'
                        svg_content = svg_content.replace(svg_start_tag, svg_start_tag + bg_rect, 1)

                    # 2. 缩放尺寸计算
                    scale = 2.0
                    width_px = int(abs(vb_width) * scale)
                    height_px = int(abs(vb_height) * scale)

                    # cairosvg 使用 scale 参数缩放，不需要显式设置 width/height
                    # svglib 需要显式的 width/height
                    if converter == 'svglib' and 'width=' not in svg_content:
                        svg_content = re.sub(
                            r'(<svg[^>]*)>',
                            rf'\1 width="{width_px}" height="{height_px}">',
                            svg_content,
                            count=1
                        )

            if converter == 'cairosvg':
                import cairosvg
                # cairosvg 会自动从 viewBox 计算尺寸，使用 scale 参数提高清晰度
                cairosvg.svg2png(bytestring=svg_content.encode('utf-8'), write_to=str(save_path),
                                  scale=2)
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
            # 如果有 file_prefix，使用 output_dir/images 目录（与 markdown 同级的 images 目录）
            # 否则使用 output_dir/database/images 目录
            if self.file_prefix:
                self.image_dir = self.output_dir / 'images'
            else:
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
        # 如果有 file_prefix，使用 file_prefix 作为文件名前缀
        if self.file_prefix:
            filename = f"{self.file_prefix}_img_{self.image_count:03d}{ext}"
        else:
            filename = f"{self.article_prefix}_img_{self.image_count:03d}{ext}" if self.article_prefix else f"img_{self.image_count:03d}{ext}"
        save_path = self.image_dir / filename

        if self._download_image(url, save_path):
            return f"images/{filename}"
        return url

    def _download_images_parallel(self, urls: List[str]) -> Dict[str, str]:
        """并行下载多个图片，返回 url -> local_path 的映射"""
        if not urls:
            return {}

        # 确保图片目录存在
        if not self.image_dir:
            if self.file_prefix:
                self.image_dir = self.output_dir / 'images'
            else:
                self.image_dir = self.output_dir / 'database' / 'images'
            self.image_dir.mkdir(parents=True, exist_ok=True)

        # 准备下载任务参数
        download_tasks = []
        for url in urls:
            if url.startswith('//'):
                url = 'https:' + url
            # 识别格式
            ext = '.jpg'
            if 'wx_fmt=png' in url or url.endswith('.png'):
                ext = '.png'
            elif 'wx_fmt=gif' in url or url.endswith('.gif'):
                ext = '.gif'
            elif 'wx_fmt=webp' in url or url.endswith('.webp'):
                ext = '.webp'

            self.image_count += 1
            if self.file_prefix:
                filename = f"{self.file_prefix}_img_{self.image_count:03d}{ext}"
            else:
                filename = f"{self.article_prefix}_img_{self.image_count:03d}{ext}" if self.article_prefix else f"img_{self.image_count:03d}{ext}"
            save_path = self.image_dir / filename
            download_tasks.append((url, save_path, filename))

        def download_one(task):
            url, save_path, filename = task
            if self._download_image(url, save_path):
                return (url, f"images/{filename}")
            return (url, url)

        # 使用 thread_map 并行下载，最大 4 线程
        results = thread_map(download_one, download_tasks, max_workers=4, desc="Downloading images", disable=len(download_tasks) <= 1)

        return dict(results)

    def _svg_to_latex(self, svg) -> Optional[str]:
        """
        从微信 SVG 数学公式中解析 LaTeX 代码

        微信使用 MathJax 渲染公式，SVG 中的 data-mml-node 属性包含 MathML 结构信息
        data-c 属性包含 Unicode 码点，可直接转换为字符
        """

        # 补充一些常用的符号映射
        EXTENDED_MAP = {
            '2217': r'\cdot',  # 星号转点乘
            '2212': '-',  # 减号
            '3F5': r'\epsilon',  # 希腊字母小 epsilon
            '2211': r'\sum',
        }

        def get_char_from_data_c(data_c: str) -> str:
            if data_c in EXTENDED_MAP: return EXTENDED_MAP[data_c]
            if data_c in SPECIAL_CHAR_MAP: return SPECIAL_CHAR_MAP[data_c]
            if data_c in MATH_ALPHANUMERIC_MAP: return MATH_ALPHANUMERIC_MAP[data_c]
            try:
                code_point = int(data_c, 16)
                if 0xE000 <= code_point <= 0xF8FF: return ''
                return chr(code_point)
            except:
                return ''
        # def get_char_from_data_c(data_c: str) -> str:
        #     """完整版：保留所有映射，同时精准过滤绘图乱码，并修复粘连问题"""
        #     if not data_c:
        #         return ''
        #
        #     res = None
        #     # --- 第一阶段：精准查表 ---
        #     if data_c in SPECIAL_CHAR_MAP:
        #         res = SPECIAL_CHAR_MAP[data_c]
        #     elif data_c in MATH_ALPHANUMERIC_MAP:
        #         res = MATH_ALPHANUMERIC_MAP[data_c]
        #     elif data_c in GREEK_BOLD_MAP:
        #         res = GREEK_BOLD_MAP[data_c]
        #     elif data_c in GREEK_BOLD_SMALL_MAP:
        #         res = GREEK_BOLD_SMALL_MAP[data_c]
        #
        #     if res is not None:
        #         # 【关键修复】如果结果是 \开头的命令且以字母结尾，加一个空格防止粘连
        #         # 例如 \gamma -> \gamma
        #         if res.startswith('\\') and res[-1].isalpha():
        #             return res + ' '
        #         return res
        #
        #     # --- 第二阶段：兜底转换与乱码过滤 ---
        #     try:
        #         code_point = int(data_c, 16)
        #         if 0xE000 <= code_point <= 0xF8FF:
        #             return ''
        #         return chr(code_point)
        #     except (ValueError, OverflowError):
        #         return ''
        # def get_char_from_data_c(data_c: str) -> str:
        #     """完整版：保留所有映射，同时精准过滤绘图乱码"""
        #     if not data_c:
        #         return ''
        #
        #     # --- 第一阶段：精准查表（保留你现有的所有特殊映射） ---
        #     if data_c in SPECIAL_CHAR_MAP:
        #         return SPECIAL_CHAR_MAP[data_c]
        #
        #     if data_c in MATH_ALPHANUMERIC_MAP:
        #         return MATH_ALPHANUMERIC_MAP[data_c]
        #
        #     if data_c in GREEK_BOLD_MAP:
        #         return GREEK_BOLD_MAP[data_c]
        #
        #     if data_c in GREEK_BOLD_SMALL_MAP:
        #         return GREEK_BOLD_SMALL_MAP[data_c]
        #
        #
        #     # --- 第二阶段：兜底转换与乱码过滤 ---
        #     try:
        #         code_point = int(data_c, 16)
        #
        #         # 【关键修复】MathJax 的 PUA (私有区) 字符过滤
        #         # 范围 U+E000 - U+F8FF 都是 MathJax 用来拼凑大括号、长箭头的“零件”
        #         # 它们在普通字体里没有对应字符，强行转码就会变成乱码方块
        #         if 0xE000 <= code_point <= 0xF8FF:
        #             return ''  # 丢弃绘图零件
        #
        #         return chr(code_point)
        #     except (ValueError, OverflowError):
        #         return ''

        # MathML node 到 LaTeX 的映射

        def parse_node(node, context='') -> str:
            """递归解析 MathML 节点"""
            if node.name == 'path':
                # 字形路径，通过 data-c 属性识别字符
                data_c = node.get('data-c', '')
                return get_char_from_data_c(data_c)

            if node.name == 'rect':  # 过滤掉根号的长横线、分数的横线等绘图零件
                return ''

            if node.name == 'text':
                # 文本节点（可能是中文注释如"选择遗忘"）
                text = node.get_text()
                return f'\\text{{{text}}}' if text else ''

            if node.name != 'g':
                # 非分组元素，直接获取子元素
                return ''.join(parse_node(child, context) for child in node.children)

            mml_node = node.get('data-mml-node', '')

            if not mml_node:
                # 没有 data-mml-node，继续解析子元素
                return ''.join(parse_node(child, context) for child in node.children)

            # 处理不同类型的 MathML 节点
            children_text = ''.join(parse_node(child, mml_node) for child in node.children)

            if mml_node == 'mi':  # 标识符
                return children_text
            elif mml_node == 'mn':  # 数字
                return children_text
            elif mml_node == 'mo':  # 运算符
                # 只要是以 \ 开头且以字母结尾的 LaTeX 命令，都建议加空格
                if children_text.startswith('\\') and children_text[-1].isalpha():
                    # 如果末尾还没有空格，则补一个
                    if not children_text.endswith(' '):
                        return children_text + ' '
                return children_text

            elif mml_node == 'mtext':  # 文本
                # 尝试从子元素中提取文本（微信 SVG 中文本在 <text> 标签内）
                text_content = collect_text_from_svg(node)
                if text_content:
                    return f'\\text{{{text_content}}}'
                return f'\\text{{{children_text}}}' if children_text else ''
            elif mml_node == 'msub':  # 下标
                parts = split_subscript_children(node)
                if len(parts) >= 2:
                    base = ''.join(parse_node(c, mml_node) for c in parts[0].children) if parts[0].name == 'g' else parse_node(parts[0], mml_node)
                    sub = ''.join(parse_node(c, mml_node) for c in parts[1].children) if parts[1].name == 'g' else parse_node(parts[1], mml_node)
                    return f'{base}_{{{sub}}}'
                return children_text
            elif mml_node == 'msubsup':  # 上下标
                parts = split_subscript_children(node)
                if len(parts) >= 3:
                    base = ''.join(parse_node(c, mml_node) for c in parts[0].children) if parts[0].name == 'g' else parse_node(parts[0], mml_node)
                    sup = ''.join(parse_node(c, mml_node) for c in parts[1].children) if parts[1].name == 'g' else parse_node(parts[1], mml_node)
                    sub = ''.join(parse_node(c, mml_node) for c in parts[2].children) if parts[2].name == 'g' else parse_node(parts[2], mml_node)
                    return f'{base}^{{{sup}}}_{{{sub}}}'
                return children_text
            elif mml_node == 'msup':  # 上标
                parts = split_subscript_children(node)
                if len(parts) >= 2:
                    base = ''.join(parse_node(c, mml_node) for c in parts[0].children) if parts[0].name == 'g' else parse_node(parts[0], mml_node)
                    # 微信 SVG 中可能将 ^ 作为单独的 mo 节点
                    # 如果 parts[1] 是 ^ 符号，需要跳过它，使用 parts[2] 作为上标
                    sup_idx = 1
                    if len(parts) >= 3:
                        # 检查 parts[1] 是否是 ^ 符号
                        check_text = ''.join(parse_node(c, mml_node) for c in parts[1].children) if parts[1].name == 'g' else parse_node(parts[1], mml_node)
                        if check_text.strip() in ['^', '^\n', '\n^']:
                            sup_idx = 2
                    sup = ''.join(parse_node(c, mml_node) for c in parts[sup_idx].children) if parts[sup_idx].name == 'g' else parse_node(parts[sup_idx], mml_node)
                    return f'{base}^{{{sup}}}'
                return children_text
            if mml_node == 'msqrt':
                # MathJax 的 msqrt 内部通常有 3 个主要部分：
                # 1. 包含被开方内容的 <g> (data-mml-node 通常是具体的 mi/mn/mrow)
                # 2. 根号符号 <g data-mml-node="mo">
                # 3. 顶部的横线 <rect>
                inner_content = ""
                for child in node.children:
                    # 排除掉作为符号零件的 mo (根号钩子) 和 rect (横线)
                    if child.name == 'g' and child.get('data-mml-node') != 'mo':
                        inner_content += parse_node(child, 'msqrt')
                    elif child.name == 'g' and child.get('data-mml-node') == 'mo':
                        continue  # 跳过钩子
                return f'\\sqrt{{{inner_content.strip()}}}'
            elif mml_node == 'mroot':  # 顺便修复 n 次根式（如 3次根号）

                parts = split_subscript_children(node)

                if len(parts) >= 2:
                    # 第一个部分是内容，第二个部分是根指数

                    base_raw = "".join(
                        parse_node(c, mml_node) for c in (parts[0].children if parts[0].name == 'g' else [parts[0]]))

                    index = "".join(
                        parse_node(c, mml_node) for c in (parts[1].children if parts[1].name == 'g' else [parts[1]]))

                    base = base_raw.replace(r'\sqrt', '').strip()

                    return f'\\sqrt[{index}]{{{base}}}'

                return children_text

            elif mml_node == 'munder':
                parts = split_subscript_children(node)
                if len(parts) >= 2:
                    base = ''.join(parse_node(c, mml_node) for c in parts[0].children) if parts[0].name == 'g' else parse_node(parts[0], mml_node)
                    under = ''.join(parse_node(c, mml_node) for c in parts[1].children) if parts[1].name == 'g' else parse_node(parts[1], mml_node)

                    # 如果 under 包含中文，通常是 \underbrace 结构
                    if any('\u4e00' <= char <= '\u9fff' for char in under):
                        # 清理 under 中可能残余的特殊空白或转义
                        clean_under = under.replace('\\text{', '').replace('}', '').strip()
                        return f'\\underbrace{{{base}}}_{{\\text{{{clean_under}}}}}'
                    return f'{{{base}}}_{{{under}}}'

            elif mml_node == 'mover':  # 上标注释
                parts = split_subscript_children(node)
                if len(parts) >= 2:
                    # parts[0] 是底座，parts[1] 是上面的装饰
                    base = ''.join(
                        parse_node(c, mml_node) for c in (parts[0].children if parts[0].name == 'g' else [parts[0]]))
                    over_raw = ''.join(
                        parse_node(c, mml_node) for c in (parts[1].children if parts[1].name == 'g' else [parts[1]]))

                    # 关键逻辑：识别并转换微信的长箭头零件
                    if r'\rightarrow' in over_raw:
                        return f'\\overrightarrow{{{base.strip()}}}'
                    if r'\leftarrow' in over_raw:
                        return f'\\overleftarrow{{{base.strip()}}}'
                    if over_raw.strip() in ['-', r'\text{-}']:
                        return f'\\overline{{{base.strip()}}}'

                    return f'{{{base}}}^{{{over_raw}}}'
                return children_text
            elif mml_node == 'munderover':  # 上下标注释（如求和符号）
                parts = split_subscript_children(node)
                if len(parts) >= 3:
                    base = ''.join(parse_node(c, mml_node) for c in parts[0].children) if parts[0].name == 'g' else parse_node(parts[0], mml_node)
                    under = ''.join(parse_node(c, mml_node) for c in parts[1].children) if parts[1].name == 'g' else parse_node(parts[1], mml_node)
                    over = ''.join(parse_node(c, mml_node) for c in parts[2].children) if parts[2].name == 'g' else parse_node(parts[2], mml_node)
                    return f'{{{base}}}_{{{under}}}^{{{over}}}'
                return children_text
            elif mml_node == 'mfrac':  # 分数
                parts = split_subscript_children(node)
                if len(parts) >= 2:
                    num = ''.join(parse_node(c, mml_node) for c in parts[0].children) if parts[0].name == 'g' else parse_node(parts[0], mml_node)
                    den = ''.join(parse_node(c, mml_node) for c in parts[1].children) if parts[1].name == 'g' else parse_node(parts[1], mml_node)
                    return f'\\frac{{{num}}}{{{den}}}'
                return children_text
            elif mml_node == 'mtable':
                rows = []
                # 找到所有的行 (mtr)
                for mtr in node.find_all('g', attrs={'data-mml-node': 'mtr'}, recursive=False):
                    cells = []
                    # 找到行内所有的单元格 (mtd)
                    for mtd in mtr.find_all('g', attrs={'data-mml-node': 'mtd'}, recursive=False):
                        cells.append(parse_node(mtd, 'mtd').strip())
                    rows.append(' & '.join(cells))

                # 如果是单列多行且带有 cases 逻辑，可以保留 cases；
                # 但如果是多列公式对齐，aligned 环境更通用
                if len(rows) > 1:
                    return '\\begin{aligned}\n' + ' \\\\\n'.join(rows) + '\n\\end{aligned}'
                return ' \\\\\n'.join(rows)
            elif mml_node == 'mtr':  # 表格行
                return children_text
            elif mml_node == 'mtd':  # 表格单元格
                return children_text
            elif mml_node == 'menclose':  # 包围框（可能是矩阵外框）
                inner = ''.join(parse_node(c, mml_node) for c in node.children)
                return inner
            elif mml_node == 'math':  # 数学根节点
                return children_text
            elif mml_node == 'mstyle':  # 样式
                return children_text
            elif mml_node == 'TeXAtom':
                return children_text
            else:
                return children_text

        def split_subscript_children(node):
            """分离下标/上标的子元素，跳过装饰性 SVG 元素"""
            parts = []
            current_part = []
            for child in node.children:
                # 跳过纯装饰性的 svg 元素（大括号等）
                if child.name == 'svg':
                    continue
                # 跳过空文本节点
                if isinstance(child, str) and not child.strip():
                    continue
                if child.name == 'g' and child.get('data-mml-node'):
                    if current_part:
                        parts.append(current_part)
                    parts.append(child)
                    current_part = []
                else:
                    current_part.append(child)
            if current_part:
                parts.append(current_part)
            return parts

        # def collect_text_from_svg(node) -> str:
        #     """从 SVG 的 text/tspan 元素中提取文本内容"""
        #     texts = []
        #     for t in node.find_all(['text', 'tspan']):
        #         txt = t.get_text()
        #         if txt:
        #             texts.append(txt)
        #     return ''.join(texts)
        def collect_text_from_svg(node) -> str:
            """修复版：仅提取叶子节点的文本，避免重复"""
            # 直接获取该节点下所有的字符串，不再通过 find_all 遍历标签
            # stripped=True 可以去掉多余空格，并合并子节点的文本
            return node.get_text(strip=True)

        try:
            # 找到 math 根节点
            math_node = svg.find('g', attrs={'data-mml-node': 'math'})
            if not math_node:
                return None

            latex = parse_node(math_node)
            return latex.strip() if latex else None
        except Exception as e:
            print(f"[Warning] Failed to parse LaTeX from SVG: {e}")
            return None

    def _process_svg_formulas(self, soup):
        """
        处理微信文章中的 SVG 数学公式

        微信使用 SVG 来渲染数学公式，通常结构为:
        <span>&nbsp;</span>  <- 占位符
        <span><svg>...</svg></span>  <- 实际公式

        SVG 中包含 aria-label 或 aria-describedby 可能有公式描述

        注意：微信 MathJax 生成的 SVG 可能是嵌套结构，外层 SVG 包含内层 SVG。
        内层 SVG（带 data-table 或 data-labels 属性）只用于布局，没有完整尺寸信息。
        我们需要跳过这些嵌套的内部 SVG，只处理最外层的 SVG。
        """
        # 确保 image_dir 存在
        if not self.image_dir:
            # 如果有 file_prefix，使用 output_dir/images 目录（与 markdown 同级的 images 目录）
            # 否则使用 output_dir/database/images 目录
            if self.file_prefix:
                self.image_dir = self.output_dir / 'images'
            else:
                self.image_dir = self.output_dir / 'database' / 'images'
            self.image_dir.mkdir(parents=True, exist_ok=True)

        # 查找所有包含数学内容的 SVG
        # 微信数学公式 SVG 通常有 role="img" 和 aria-label="插图" 或类似属性
        for svg in soup.find_all('svg'):
            # 【关键修复】跳过嵌套的内部 SVG
            # 1. 检查是否被包含在另一个 SVG 中
            if svg.find_parent('svg'):
                continue

            # 2. 跳过 MathJax 内部布局用的 SVG（data-table 或 data-labels）
            # 这些是嵌套在外层 SVG 内部的，用于表格布局或标签定位
            if svg.get('data-table') or svg.get('data-labels'):
                continue

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

            # 优先尝试从 SVG 解析 LaTeX 公式
            latex = self._svg_to_latex(svg)
            if latex:
                # 判断是块级公式还是行内公式
                # 检查是否包含 mtable (矩阵/方程组) 或 menclose (带框公式)
                has_block = svg.find(attrs={'data-mml-node': ['mtable', 'menclose']})
                if has_block:
                    replacement = f'\n\n$$\n{latex}\n$$\n\n'
                else:
                    replacement = f' ${latex}$ '

                # 移除占位 span
                if nbsp_span:
                    nbsp_span.decompose()

                # 替换整个父 span (包含 SVG 的那个)
                parent_span.replace_with(replacement)
                continue

            # 解析失败，回退到 PNG 图片
            svg_content = str(svg)
            self.formula_count += 1
            # 如果有 file_prefix，使用 file_prefix 作为文件名前缀
            if self.file_prefix:
                filename = f"{self.file_prefix}_formula_{self.formula_count:03d}.png"
            else:
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

        # 2. 处理图片和表情（多线程下载）
        # 先收集所有需要下载的图片
        img_elements = []
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('data-original') or img.get('src')
            if src:
                if 'emoji' in img.get('class', []) or 'biaoqing' in src:
                    alt = img.get('alt', '')
                    img.replace_with(alt if alt else "")
                else:
                    img_elements.append((img, src))

        # 并行下载图片
        if img_elements:
            urls = [src for _, src in img_elements]
            local_paths = self._download_images_parallel(urls)

            # 替换图片引用
            for img, src in img_elements:
                local_path = local_paths.get(src, src)
                img.replace_with(f'![]({local_path})')

        # 3. 处理代码块 (优化版)
        for pre in soup.find_all(['pre', 'section']):
            # 微信代码块特征：通常带有 code-snippet__js 等 class
            # 或者是 mdnice编辑器 格式 (data-tool="mdnice编辑器")
            is_code = 'code-snippet' in str(pre.get('class', '')) or pre.name == 'pre'
            if not is_code:
                continue

            # 检测是否为 mdnice编辑器 格式
            is_mdnice = pre.get('data-tool') == 'mdnice编辑器'

            # 尝试定位真正的代码容器
            code_tag = pre.find('code')

            # 核心修复：微信代码块每一行通常是一个 section 或 p
            # 如果直接 get_text() 会丢失换行。我们需要手动遍历子节点并换行。
            lines = []

            if is_mdnice:
                # mdnice编辑器 格式：代码在 <span leaf=""> 中，<br> 表示换行
                # 需要递归遍历所有节点，提取文本并保留换行
                def extract_mdnice_text(node):
                    """递归提取 mdnice 格式的代码文本"""
                    if isinstance(node, str):
                        return node
                    if node.name is None:
                        return node.get_text()
                    if node.name == 'br':
                        return '\n'
                    # 检查是否有 leaf 属性（span leaf=""）
                    # 对于有 leaf 属性的 span，需要检查子节点
                    if node.name == 'span':
                        # 先收集所有子节点的内容
                        parts = []
                        for child in node.children:
                            text = extract_mdnice_text(child)
                            if text:
                                parts.append(text)
                        return ''.join(parts)
                    # 其他标签递归处理
                    parts = []
                    for child in node.children:
                        text = extract_mdnice_text(child)
                        if text:
                            parts.append(text)
                    return ''.join(parts)

                code_text = extract_mdnice_text(code_tag) if code_tag else extract_mdnice_text(pre)
                lines = code_text.split('\n')
            else:
                # 寻找行容器（微信常用 code-snippet__line-content）
                line_containers = pre.find_all(class_=re.compile(r'line-content|code-snippet__line'))

                if line_containers:
                    for line in line_containers:
                        lines.append(line.get_text())
                else:
                    # 备选方案：如果没找到行容器，尝试处理普通的换行
                    raw_text = code_tag.get_text('\n') if code_tag else pre.get_text('\n')
                    lines = raw_text.split('\n')

            # 过滤掉纯数字的行号（微信有些代码块行号在 text 里）
            # 同时清理零宽空格和不间断空格
            clean_lines = []
            for l in lines:
                content = l.replace('\u200b', '').replace('\xa0', ' ').strip('\r')
                clean_lines.append(content)

            code_text = '\n'.join(clean_lines)

            # 自动识别语言（微信通常在 data-lang 属性里）
            lang = pre.get('data-lang') or ""
            if not lang and code_tag and code_tag.get('class'):
                lang_match = re.search(r'language-(\w+)', ' '.join(code_tag.get('class')))
                if lang_match:
                    lang = lang_match.group(1)

            # 替换为标准的 Markdown 格式
            pre.replace_with(f'\n\n```{lang}\n{code_text}\n```\n\n')

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
            for tr in node.find_all('tr'):
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
        # 如果有 file_prefix，直接保存到 output_dir 根目录，文件名为 {file_prefix}.md
        # 否则保存到 output_dir/database/ 目录
        if self.file_prefix:
            output_path = self.output_dir / f"{self.file_prefix}.md"
        else:
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