# SendArticle2Kindle

[English](README.md) | [中文](README_chn.md)

一个 [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) 服务器：从网页下载文章，转为 Markdown，再转换为 EPUB / KFX 电子书格式推送到墨水屏阅读器——对数学公式、图片、代码块有专门优化。

## 功能概览

```
URL（知乎 / 微信 / arXiv）
  │
  ▼
┌──────────────────┐     ┌─────────────┐     ┌──────────────────┐
│  文章下载器        │──▶│  Markdown  │──▶│  md2kfx 转换器    │
│  (zhihu/wechat/   │   │  (.md)     │   │  LaTeX→MathML     │
│   arxiv)          │   │            │   │  代码→图片         │
└──────────────────┘     └─────────────┘   │  图片→PNG          │
                                            │  自动目录          │
                                            └────────┬─────────┘
                                                     │
                                            ┌────────▼─────────┐
                                            │  EPUB + KFX      │
                                            │  推送到阅读器      │
                                            └──────────────────┘
```

**支持来源：**
- 知乎专栏 / 回答
- 微信公众号文章
- arXiv 论文（HTML 或 TeX 源码）
- 任意本地 Markdown 文件

**输出格式：**
- **KFX** — Amazon 增强排版格式（仅 Kindle）
- **EPUB** — 通用格式（Kobo、文石 Boox、reMarkable 等）

---

## MCP 服务器

本项目以 MCP 服务器形式运行。任何兼容 MCP 的 AI Agent（Claude Desktop、Claude Code、Hermes Agent 等）都可以直接在对话中调用其工具。

### 传输模式

| 模式 | 命令 | 适用场景 |
|------|------|---------|
| **stdio** | `python mcp_server.py --transport stdio` | 生产使用：AI Agent 自动管理进程 |
| **sse**（默认） | `python mcp_server.py` | 开发调试：IDE 断点、热重载 |

### 各 Agent 配置方式

#### Hermes Agent

在 `config.yaml`（Windows: `%AppData%\Local\hermes\config.yaml`）中添加：

```yaml
mcp_servers:
  tokindle:
    command: /path/to/your/python
    args:
      - /path/to/tokindle/mcp_server.py
      - --transport
      - stdio
```

#### Claude Desktop

编辑 `claude_desktop_config.json`（Windows: `%APPDATA%\Claude\`）：

```json
{
  "mcpServers": {
    "tokindle": {
      "command": "/path/to/your/python",
      "args": ["/path/to/tokindle/mcp_server.py", "--transport", "stdio"],
      "env": {}
    }
  }
}
```

#### Claude Code

```bash
# stdio 模式
/mcp add python /path/to/tokindle/mcp_server.py -- --transport stdio

# SSE 模式（先启动服务，再连接）
python mcp_server.py
/mcp add sse http://127.0.0.1:48000/sse
```

### 常用提问方式

直接和 AI Agent 对话即可，它会自动调用对应工具。

**下载 & 转换：**
- `下载这篇知乎文章: https://zhuanlan.zhihu.com/p/xxx`
- `把这篇微信公众号文章转成电子书: https://mp.weixin.qq.com/s/xxx`
- `下载这篇 arXiv 论文: https://arxiv.org/abs/2607.07508`
- `批量下载这几篇文章: url1, url2, url3`

**推送到阅读器：**
- `把这篇文章推送到 Kindle`
- `检查 Kindle 是否已连接`
- `搜索一下有没有已经转好的 "Kimi Linear"`
- `把这篇用 EPUB 格式推送`

**arXiv TeX 源码（深度模式，公式/图片更完整）：**
- `用 TeX 源码转换这篇论文: https://arxiv.org/abs/2607.07508`
- `下载这篇论文的 TeX 源码，转成 KFX，加一份中文导读`

**文件管理：**
- `列一下所有已转换的文件`
- `删掉文件 abc123`
- `Kindle 上有哪些文件？`

**排查问题（KFX 转换失败时）：**
- `这篇转换失败了，帮我查一下原因`
- `检查一下这个 MD 文件的公式分隔符有没有问题`

### MCP 工具一览

| 工具 | 说明 |
|------|------|
| `download_and_convert` | 从 URL 下载 → MD → EPUB/KFX |
| `batch_download_and_convert` | 批量下载 |
| `upload_local_file` | 上传本地 .md 文件并转换 |
| `send_to_kindle` | 推送文件到 Kindle |
| `check_kindle_connection` | 检查 Kindle 连接状态 |
| `list_kindle_files` | 列出 Kindle 上的文件 |
| `list_files` / `search_files` | 浏览/搜索已转换文件 |
| `get_file_info` / `delete_file` | 文件管理 |
| `config_upload_path` | 修改 Kindle 目标路径 |

---

## KFX 转换：特殊支持

`md2kfx.py` 转换流程对三类内容做了专门处理：

### 数学公式（LaTeX → MathML）

行内公式 `$E = mc^2$` 和块级公式 `$$\sum_{i=1}^{N} x_i$$` 通过 `latex2mathml` 转为 MathML，由 Kindle KFX 引擎渲染。

支持的 LaTeX 命令：
- 希腊字母、分数、求和、积分
- `\mathbf`、`\mathcal`、`\mathbb`、`\mathrm`
- `\hat`、`\bar`、`\tilde`、`\frac`、`\sqrt`
- `\begin{cases}...\end{cases}`、`\begin{aligned}...\end{aligned}`
- `\cancel`、`\textcolor`（去除颜色，保留内容）

降级方案：`--skip-mathml` 参数将公式转为纯文本方括号 `[...]`。

### 代码块 → 图片

带语法高亮的代码块通过 Pygments 渲染为图片，适配墨水屏尺寸。避免了 Kindle 上原始代码的字体和间距问题。

### 图片处理

- 远程图片自动下载并嵌入
- GIF/WebP/BMP → PNG 转换
- PDF 图表 → PNG（通过 pymupdf，用于 arXiv TeX 源码流程）

### 自动目录

标题层级（`#`/`##`/`###`）自动解析为可导航目录，带锚点 ID。

---

## Skills（AI Agent 工作流）

三个可复用的技能模块，为 AI Agent 提供结构化工作流：

### 1. `tex_to_kindle` — arXiv TeX 源码 → KFX

从 arXiv 论文 **TeX 源码**（非 HTML）完整转换：

- 多文件 `\input{}` 解析
- 自定义宏展开（`\newcommand`、`\def`）
- 数学环境 → `$$...$$`（保留 LaTeX 供 MathML 转换）
- PDF 图表 → PNG（通过 pymupdf）
- 表格、算法块、定理环境
- **KFX 转换前公式分隔符校验**（Step 2.5）
- AI 生成中文论文导读（12 节分析框架）

```bash
python skills/tex_to_kindle/scripts/tex2md.py \
  --tex-dir /path/to/extracted/tex \
  --output paper.md \
  --title "论文标题" --author "作者"
```

### 2. `merge_books` — 双语电子书制作

将中英文 EPUB 电子书合并为**中英对照**阅读版本，带词汇注释。

- EPUB 章节自动拆分
- 按段落对齐（长度 + 翻译相似度）
- CET-4 / CET-6 词汇标注
- 中文在前、英文在后，逐段交替

```bash
# 拆分章节
python skills/merge_books/scripts/extract_chapters.py \
  --en english.epub --zh chinese.epub --out book_dir

# 合并输出
python skills/merge_books/scripts/merge_md.py --dir book_dir/markdown --title "书名"
```

### 3. 排查工具

#### 3.1 `md-math-check` — 公式分隔符检查

**任意** Markdown 文件的通用预检工具。检测 `$`/`$$` 配对问题，防止垃圾 MathML 导致 KFX 转换崩溃。

```bash
python scripts/check_math_delimiters.py input.md
```

输出 JSON 报告，包含问题类型、行号、上下文和修复建议：
- `ODD_DD_COUNT` / `ODD_D_COUNT` — 分隔符数量为奇数（未配对）
- `STRAY_DD` — 行中间的 `$$`（应为 `$`）
- `MISPAIRED_DD` — `$$` 对内包含标题/正文（非公式内容）
- `EMPTY_DD_PAIR` — `$$` 紧跟 `$$`（空公式）

AI Agent 读取报告 → 修复 Markdown → 重新检查，直到无问题。适用于 arXiv、知乎、微信等任何来源。

#### 3.2 `fix_tokindle` — KFX 转换失败排查

当 KFX 转换报 *"Kindle conversion has encountered an internal error"* 时，提供：
- 转换流程概览（MD → HTML → EPUB → KFX）
- 已知故障点目录（FP1–FP6b）
- 诊断方法（EPUB XHTML 检查、公式追踪、详细日志）
- 二分法定位问题内容

---

## 安装

### 前置条件

| 组件 | 需要用于 | 说明 |
|------|---------|------|
| Python 3.8+ | 所有功能 | |
| `pip install -r requirements.txt` | 所有功能 | markdown, bs4, latex2mathml, EbookLib 等 |
| [Calibre](https://calibre-ebook.com/download) | KFX 输出 | 提供 `ebook-convert` 命令 |
| [Kindle Previewer 3](https://www.amazon.com/Kindle-Previewer/b?ie=UTF8&node=21381691011) | KFX 输出 | KFX 渲染引擎 |
| [KFX Output 插件](https://www.mobileread.com/forums/showthread.php?t=291290) | KFX 输出 | Calibre 插件 |
| [pymupdf](https://pypi.org/project/PyMuPDF/) | arXiv TeX 源码 | PDF 图表 → PNG |
| [Playwright](https://playwright.dev/) | 浏览器模式下载 | 可选 |

> **仅用 EPUB 的用户**（Kobo、文石等）：无需安装 Calibre / Kindle Previewer / KFX 插件。

### 快速安装

```bash
git clone https://github.com/ia-xu/SendArticle2Kindle.git
cd SendArticle2Kindle
pip install -r requirements.txt

# KFX 用户（Kindle）：
#   1. 安装 Calibre: https://calibre-ebook.com/download
#   2. 安装 Kindle Previewer 3
#   3. 在 Calibre 中安装 KFX Output 插件

# arXiv TeX 源码用户：
pip install pymupdf
```

---

## Web UI

提供 Flask Web 界面，无需 AI Agent 即可粘贴链接、上传文件、推送到阅读器。

![Web UI](articles/img.png)

```bash
python webui/app.py
# 打开 http://127.0.0.1:5006
```

📖 **项目介绍（知乎）**: [网络文章转 Kindle 电子书工具](https://zhuanlan.zhihu.com/p/2019355339670189711)

详细的 Web UI 和命令行使用说明（Cookie 获取、浏览器模式、批量操作），见 [`README_v0.1.0.md`](README_v0.1.0.md)。

---

## 项目结构

```
SendArticle2Kindle/
├── mcp_server.py              # MCP 服务器入口
├── src/
│   ├── md2kfx.py              # MD → EPUB → KFX 核心转换器
│   ├── downloader/            # 文章下载器
│   │   ├── zhihu2markdown.py
│   │   ├── wechat2markdown.py
│   │   └── arxiv2markdown.py
│   ├── config.py              # 配置文件
│   └── tools/                 # 数据库、Kindle 设备、文件管理
├── scripts/
│   └── check_math_delimiters.py  # 公式分隔符检查工具
├── skills/                    # AI Agent 工作流模块
│   ├── tex_to_kindle/         # arXiv TeX → KFX（含论文导读）
│   ├── merge_books/           # 双语电子书合并
│   ├── md-math-check/         # 公式分隔符检查
│   └── fix_tokindle/          # KFX 调试指南
├── webui/                     # Flask Web 界面
├── outputs/                   # 转换输出目录
├── requirements.txt
└── README.md
```

---

## License

MIT
