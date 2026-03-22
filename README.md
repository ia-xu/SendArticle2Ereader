# toKindle

将网络文章转换为 Kindle 友好格式的工具集。

- 目前仅支持了 windows / mac 尚未适配 ， 欢迎大佬帮个忙测测，改改代码
- 目前对于 kpw6 等设备:
  - windows 中 kpw6 等使用的是 MTP（媒体传输协议） 模式，在Windows中显示为便携设备/媒体设备，而不是传统的U盘模式（大容量存储设备）
  - 连接后windows 不会给设备分配盘符，因此无法直接使用该 webui 导入到kindle
  - 只能够将本地的一个文件夹当作 kindle 导出的文件夹 (修改 src/config.py 中的 KINDLE_ARTICLE_PATH)
  - 然后手动将转换好的 kfx 导入内容到 kindle 当中
  - 欢迎大佬帮个忙想个办法 : )

## 项目功能与目标

本项目旨在帮助用户将网络文章（知乎专栏、微信公众号、arXiv 论文等）转换为 Kindle 设备可读的 KFX 格式电子书。

**核心功能：**

- **知乎文章下载**：抓取知乎专栏文章并转换为 Markdown，支持公式、代码块、图片等
- **微信公众号文章下载**：抓取微信公众号文章，保留原文格式
- **arXiv 论文下载**：从 arXiv 下载学术论文，转换为 Markdown 格式
- **Markdown 转 KFX**：将 Markdown 文件转换为 Kindle KFX 格式，支持目录、数学公式、代码高亮等
- **Web 界面**：提供简洁的 Web 界面，一站式完成下载和转换

**转换特点：**

- 数学公式支持（LaTeX/MathML）
- 代码块语法高亮并转为图片（适配 Kindle）
- 自动生成目录
- 图片自动下载并优化
- 支持 EPUB/KFX 输出

---

## 目录结构

```
tokindle/
├── src/
│   ├── downloader/                    # 文章下载器模块
│   │   ├── zhihu2markdown.py          # 知乎文章下载器
│   │   ├── wechat2markdown.py         # 微信公众号下载器
│   │   └── arxiv2markdown.py          # arXiv 论文下载器
│   └── md2kfx.py                      # Markdown 转 KFX 核心模块
├── webui/
│   ├── app.py                         # Flask Web 服务
│   └── templates/
│       └── index.html                 # Web 界面模板
├── config/
│   ├── zhihu_cookies.json             # 知乎登录 Cookie（自动生成）
│   └── wechat_cookies.json            # 微信 Cookie（自动生成）
├── uploads/                           # 上传文件临时目录
├── outputs/                           # 转换输出目录
├── database/                          # 文章数据库目录
├── misc/                              # 辅助工具脚本
├── requirements.txt                   # Python 依赖
├── start_webui.bat                    # Windows 启动脚本
└── README.md                          # 本文档
```

---

## 安装指南

### 第一步：安装 Python

**Windows 用户：**

1. 访问 [Python 官网](https://www.python.org/downloads/) 下载 Python 3.8 或更高版本
2. 运行安装程序，**务必勾选 "Add Python to PATH"**（将 Python 添加到环境变量）
3. 打开命令提示符（按 Win+R，输入 `cmd`，回车），输入以下命令验证安装：
   ```bash
   python --version
   ```

**Mac 用户：**

Mac 通常已预装 Python。打开终端，输入：
```bash
python3 --version
```

### 第二步：下载项目

**方式一：使用 Git（推荐）**

```bash
git clone https://github.com/your-username/tokindle.git
cd tokindle
```

**方式二：直接下载**

1. 点击项目页面的 "Code" -> "Download ZIP"
2. 解压到任意目录
3. 进入解压后的目录

### 第三步：创建虚拟环境（推荐）

**Windows：**
```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate
```

**Mac/Linux：**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 第四步：安装依赖

```bash
pip install -r requirements.txt
```

依赖列表：
- markdown - Markdown 解析
- beautifulsoup4 - HTML 解析
- requests - HTTP 请求
- Pillow - 图片处理
- EbookLib - EPUB 生成
- pygments - 代码语法高亮
- flask - Web 框架
- latex2mathml - LaTeX 公式转换

### 第五步：安装 Calibre 和 Kindle Previewer 3（KFX 转换必需）

如需将 Markdown 转换为 KFX 格式，**必须同时安装以下两个软件**：

#### 5.1 安装 Calibre

1. 访问 [Calibre 官网](https://calibre-ebook.com/download) 下载安装
2. 安装完成后，确保 `ebook-convert` 命令可用
3. Windows 用户可能需要将 Calibre 安装目录（默认 `C:\Program Files\Calibre2`）添加到系统环境变量 PATH

#### 5.2 安装 Kindle Previewer 3

1. 访问 [Amazon Kindle Previewer 3 下载页面](https://www.amazon.com/Kindle-Previewer/b?ie=UTF8&node=21381691011) 下载
2. 或直接下载：[Windows 版本](https://kindlepreviewer.s3.amazonaws.com/KindlePreviewerInstaller.exe)
3. 运行安装程序，按提示完成安装
4. 安装完成后，Kindle Previewer 会自动注册 KFX 转换插件到 Calibre

#### 5.3 安装 KFX Output 插件（Calibre 插件）

安装完 Calibre 后，还需要安装 KFX Output 插件：

1. 打开 Calibre
2. 点击菜单 **首选项** (Preferences) → **插件** (Plugins)
3. 点击 **获取新插件** (Get new plugins)
4. 搜索 **"KFX Output"**
5. 选择该插件并点击 **安装** (Install)
6. 安装完成后重启 Calibre

**或者手动安装：**

1. 从 [Calibre 插件页面](https://www.mobileread.com/forums/showthread.php?t=291290) 下载 KFX Output 插件 zip 文件
2. 打开 Calibre → 首选项 → 插件
3. 点击 **从文件加载插件** (Load plugin from file)
4. 选择下载的 zip 文件安装
5. 重启 Calibre

**重要说明：**
- Calibre 负责 EPUB 生成和格式转换
- Kindle Previewer 3 提供 KFX 渲染引擎
- KFX Output 插件将两者连接，实现 EPUB → KFX 转换
- 三个组件缺一不可，否则 KFX 转换会失败

### 第六步：安装 Playwright（可选，用于浏览器模式）

部分网站需要使用浏览器模式抓取：

```bash
pip install playwright
playwright install chromium
```

---

## 使用指南

### 方式一：Web 界面（推荐新手）

> **重要提示：使用 Web 界面前，请先登录获取 Cookie！**
>
> - 知乎文章下载：需要先完成知乎登录获取 Cookie，详见 [知乎 Cookie 获取方法](#知乎-cookie-获取方法)
> - 微信公众号下载：部分文章需要登录，详见 [微信公众号 Cookie 获取方法](#微信公众号-cookie-获取方法)
> - arXiv 论文下载：无需登录，可直接使用
>
> 未获取 Cookie 时，Web 界面的知乎和微信下载功能将无法正常工作。

**启动服务：**

**Windows：**
双击 `start_webui.bat` 文件

**或手动启动：**
```bash
cd tokindle
python webui/app.py
```

启动后，浏览器访问 http://127.0.0.1:5000 即可使用 Web 界面。

**Web 界面功能：**

1. **文章下载**：输入知乎/微信/arXiv 链接，一键下载文章
2. **文件上传**：上传本地 Markdown 文件进行转换
3. **格式转换**：将 Markdown 转换为 KFX/EPUB 格式
4. **批量处理**：支持批量下载和转换

---

### 方式二：命令行使用

#### 1. 知乎文章下载器 (zhihu2markdown)

将知乎专栏文章转换为 Markdown 格式。

**登录获取 Cookie（首次使用推荐）：**

```bash
# 交互式登录，会打开浏览器让你手动登录
python "src/downloader/zhihu2markdown.py" login
```

登录成功后，Cookie 会自动保存到 `config/zhihu_cookies.json`。

**其他登录方式：**

```bash
# 从浏览器复制 Cookie 字符串
python "src/downloader/zhihu2markdown.py" login -c "z_c0=xxx; _xsrf=yyy"

# 检查登录状态
python "src/downloader/zhihu2markdown.py" login --check
```

**下载文章：**

```bash
# 基本用法（使用已保存的 Cookie）
python "src/downloader/zhihu2markdown.py" fetch https://zhuanlan.zhihu.com/p/123456789

# 指定输出目录
python "src/downloader/zhihu2markdown.py" fetch https://zhuanlan.zhihu.com/p/123456789 -o ./output

# 强制使用浏览器模式（应对反爬）
python "src/downloader/zhihu2markdown.py" fetch https://zhuanlan.zhihu.com/p/123456789 --browser
```

**支持的 URL 格式：**

- 专栏文章：`https://zhuanlan.zhihu.com/p/123456789`
- 问题回答：`https://www.zhihu.com/question/xxx/answer/yyy`

**命令一览：**

| 命令 | 说明 |
|------|------|
| `login` | 交互式登录，打开浏览器手动登录 |
| `login -c "cookie"` | 从字符串导入 Cookie |
| `login --check` | 检查登录状态 |
| `fetch <url>` | 下载文章 |
| `fetch <url> -o dir` | 指定输出目录 |
| `fetch <url> --browser` | 浏览器模式下载 |

---

#### 2. 微信公众号文章下载器 (wechat2markdown)

将微信公众号文章转换为 Markdown 格式。

**设置 Cookie（部分文章需要）：**

```bash
# 交互式登录（会打开浏览器让你扫码登录微信）
python "src/downloader/wechat2markdown.py" login

# 从浏览器复制 Cookie 字符串
python "src/downloader/wechat2markdown.py" login -c "cookie字符串"

# 检查登录状态
python "src/downloader/wechat2markdown.py" login --check
```

**下载文章：**

```bash
# 使用文章 URL
python "src/downloader/wechat2markdown.py" fetch "https://mp.weixin.qq.com/s/xxx"

# 指定输出目录
python "src/downloader/wechat2markdown.py" fetch "https://mp.weixin.qq.com/s/xxx" -o ./output
```

**支持的输入格式：**

- 微信文章链接：`https://mp.weixin.qq.com/s/xxx`

**命令一览：**

| 命令 | 说明 |
|------|------|
| `login` | 交互式登录 |
| `login -c "cookie"` | 从字符串导入 Cookie |
| `login --check` | 检查登录状态 |
| `fetch <url>` | 下载文章 |
| `fetch <url> -o dir` | 指定输出目录 |

---

#### 3. arXiv 论文下载器 (arxiv2markdown)

将 arXiv 论文转换为 Markdown 格式。

**特点：**

- 无需登录
- 支持数学公式（LaTeX 格式）
- 自动提取标题、作者、摘要

**下载论文：**

```bash
# 基本用法
python "src/downloader/arxiv2markdown.py" https://arxiv.org/html/2602.02276v1

# 或使用 abs 链接（自动转换为 html 链接）
python "src/downloader/arxiv2markdown.py" https://arxiv.org/abs/2602.02276

# 指定输出目录
python "src/downloader/arxiv2markdown.py" https://arxiv.org/html/2602.02276v1 -o ./output

# 自定义标题和作者
python "src/downloader/arxiv2markdown.py" https://arxiv.org/html/2602.02276v1 -t "论文标题" -a "作者"
```

**支持的 URL 格式：**

- HTML 页面：`https://arxiv.org/html/2602.02276v1`
- 摘要页面：`https://arxiv.org/abs/2602.02276`

**命令一览：**

| 命令 | 说明 |
|------|------|
| `fetch <url>` | 下载论文 |
| `fetch <url> -o dir` | 指定输出目录 |
| `fetch <url> -t "标题"` | 自定义标题 |
| `fetch <url> -a "作者"` | 自定义作者 |

---

#### 4. Markdown 转 KFX (md2kfx.py)

将 Markdown 文件转换为 Kindle KFX 格式。

**基本用法：**

```bash
python src/md2kfx.py input.md -o output.kfx -a "作者名"
```

**参数说明：**

| 参数 | 说明 |
|------|------|
| `input` | 输入的 Markdown 文件路径 |
| `-o, --output` | 输出文件路径（可选，默认与输入同名） |
| `-a, --author` | 作者名称（可选，默认 "Kindle User"） |
| `--skip-mathml` | 跳过 MathML 转换（提高 KFX 兼容性） |

**示例：**

```bash
# 基本转换
python src/md2kfx.py article.md

# 指定输出文件和作者
python src/md2kfx.py article.md -o mybook.kfx -a "张三"

# 跳过数学公式转换
python src/md2kfx.py article.md --skip-mathml
```

**转换特性：**

- 自动下载远程图片
- 代码块转为语法高亮图片
- 数学公式支持（LaTeX/MathML）
- 自动生成目录
- 图片格式优化（GIF/WebP 转 PNG）

---

## 如何获取 Cookie

### 知乎 Cookie 获取方法

**方式一：使用自动登录（推荐）**

```bash
python "src/downloader/zhihu2markdown.py" login
```

程序会自动打开浏览器，登录后自动保存 Cookie。

**方式二：手动从浏览器获取**

1. 浏览器访问 https://www.zhihu.com 并登录
2. 按 F12 打开开发者工具
3. 切换到 "Network"（网络）标签
4. 刷新页面
5. 点击任意请求，在 "Headers"（请求头）中找到 "Cookie"
6. 复制 Cookie 值

```bash
# 保存 Cookie
python "src/downloader/zhihu2markdown.py" login -c "你复制的Cookie"
```

### 微信公众号 Cookie 获取方法

与知乎类似，访问微信公众号文章页面后从开发者工具获取 Cookie。

---

## 常见问题

### Q: 提示 401/403 错误？

A: 需要先登录获取 Cookie：

```bash
python "src/downloader/zhihu2markdown.py" login
```

### Q: 图片无法显示？

A:
- 知乎图片可能需要正确的 Referer 才能显示
- 建议使用 Web 界面转换，会自动下载图片

### Q: KFX 转换失败？

A: 确保 KFX 转换所需的三个组件都已正确安装：

1. **Calibre** - 确保已安装且 `ebook-convert` 命令可用
2. **Kindle Previewer 3** - 确保已安装（提供 KFX 渲染引擎）
3. **KFX Output 插件** - 确保已在 Calibre 中安装该插件

检查步骤：
- 打开 Calibre → 首选项 → 插件，确认 KFX Output 插件已启用
- 确认 Kindle Previewer 3 已安装并能正常打开
- 尝试在 Calibre 中手动转换一本 EPUB 为 KFX，测试是否成功

如果仍有问题，尝试使用 `--skip-mathml` 参数跳过数学公式转换。

### Q: 浏览器模式报错？

A: 安装 Playwright：

```bash
pip install playwright
playwright install chromium
```

### Q: Windows 下中文乱码？

A: 确保终端编码为 UTF-8：
```bash
chcp 65001
```

---

## 依赖说明

| 依赖 | 用途 |
|------|------|
| markdown | Markdown 解析和转换 |
| beautifulsoup4 | HTML 内容解析 |
| requests | HTTP 请求处理 |
| Pillow | 图片处理和格式转换 |
| EbookLib | EPUB 电子书生成 |
| pygments | 代码语法高亮 |
| flask | Web 服务框架 |
| latex2mathml | LaTeX 公式转 MathML |
| playwright | 浏览器自动化（可选） |

---

## License

MIT License