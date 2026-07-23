# SendArticle2Kindle

[English](README.md) | [中文](README_chn.md)

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that downloads web articles, converts them to Markdown, then transforms Markdown into EPUB and KFX for e-readers — with first-class support for math formulas, images, and code blocks.

## What It Does

```
URL (Zhihu / WeChat / arXiv)
  │
  ▼
┌──────────────────┐     ┌─────────────┐     ┌──────────────────┐
│  Article Downloader │──▶│  Markdown  │──▶│  md2kfx Converter │
│  (zhihu/wechat/    │   │  (.md)     │   │  LaTeX→MathML     │
│   arxiv)           │   │            │   │  Code→Image       │
└──────────────────┘     └─────────────┘   │  Image→PNG        │
                                            │  TOC Generation   │
                                            └────────┬─────────┘
                                                     │
                                            ┌────────▼─────────┐
                                            │  EPUB + KFX      │
                                            │  (push to Kindle) │
                                            └──────────────────┘
```

**Supported sources:**
- Zhihu columns & answers (知乎专栏/回答)
- WeChat Official Account articles (微信公众号)
- arXiv papers (HTML or TeX source)
- Any local Markdown file (manual upload)

**Supported output formats:**
- **KFX** — Amazon's enhanced typesetting format (Kindle only)
- **EPUB** — Universal format (Kobo, Boox, reMarkable, etc.)

---

## MCP Server

This project runs as an MCP server. Any MCP-compatible AI agent (Claude Desktop, Claude Code, Hermes Agent, etc.) can call its tools directly in conversation.

### Quick Start

```bash
# 1. Clone
git clone https://github.com/ia-xu/SendArticle2Kindle.git
cd SendArticle2Kindle

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) For KFX output: install Calibre + Kindle Previewer 3
#    See README_v0.1.0.md for detailed setup

# 4. Run as MCP server (stdio mode, managed by your AI agent)
python mcp_server.py --transport stdio
```

### Transport Modes

The server supports two transport protocols:

| Mode | Command | Use Case |
|------|---------|----------|
| **stdio** | `python mcp_server.py --transport stdio` | Production: AI agent auto-manages the process lifecycle |
| **sse** (default) | `python mcp_server.py` | Development: run as HTTP server, debug in IDE with breakpoints |

### MCP Configuration by Agent

#### Hermes Agent

Add to `config.yaml` (`%AppData%\Local\hermes\config.yaml` on Windows):

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

Add to `claude_desktop_config.json` (`%APPDATA%\Claude\` on Windows):

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
# Auto-add (stdio mode)
/mcp add python /path/to/tokindle/mcp_server.py -- --transport stdio

# Or SSE mode (start server first, then connect)
python mcp_server.py                          # starts on port 48000
/mcp add sse http://127.0.0.1:48000/sse
```

> See [`README_v0.1.0.md`](README_v0.1.0.md) for SSE debugging workflow (IDE breakpoints, hot reload).

### Usage Examples

Talk to your AI agent naturally — it auto-selects the right MCP tool.

**Download & Convert:**
- `下载这篇知乎文章: https://zhuanlan.zhihu.com/p/xxx`
- `把这篇微信公众号文章转成电子书: https://mp.weixin.qq.com/s/xxx`
- `下载这篇 arXiv 论文: https://arxiv.org/abs/2607.07508`
- `批量下载这几篇文章: url1, url2, url3`

**Push to Kindle:**
- `把这篇文章推送到 Kindle`
- `检查 Kindle 是否已连接`
- `搜索一下有没有已经转好的 "Kimi Linear"`
- `把这篇用 EPUB 格式推送（不用 KFX）`

**arXiv TeX Source（深度模式，公式/图片更完整）:**
- `用 TeX 源码转换这篇论文: https://arxiv.org/abs/2607.07508`
- `下载这篇论文的 TeX 源码，转成 KFX，加一份中文导读`

**File Management:**
- `列一下所有已转换的文件`
- `删掉文件 abc123`
- `Kindle 上有哪些文件？`

**Troubleshooting（KFX 转换失败时）:**
- `这篇转换失败了，帮我查一下原因`
- `检查一下这个 MD 文件的公式分隔符有没有问题`

### MCP Tools

| Tool | Description |
|------|-------------|
| `download_and_convert` | Download a URL → MD → EPUB/KFX |
| `batch_download_and_convert` | Batch download multiple URLs |
| `upload_local_file` | Upload & convert a local .md file |
| `send_to_kindle` | Push converted file to Kindle via USB |
| `check_kindle_connection` | Check if Kindle is connected |
| `list_kindle_files` | List files on connected Kindle |
| `list_files` / `search_files` | Browse/search converted files |
| `get_file_info` / `delete_file` | File management |
| `config_upload_path` | Change Kindle target directory |

---

## KFX Conversion: Special Support

The `md2kfx.py` pipeline handles three things that normally break e-reader formatting:

### Math Formulas (LaTeX → MathML)

Inline math `$E = mc^2$` and block math `$$\sum_{i=1}^{N} x_i$$` are converted to [MathML](https://www.w3.org/Math/) via `latex2mathml`, then rendered by Kindle's KFX engine.

Supported LaTeX in formulas:
- Greek letters, fractions, sums, integrals
- `\mathbf`, `\mathcal`, `\mathbb`, `\mathrm`
- `\hat`, `\bar`, `\tilde`, `\frac`, `\sqrt`
- `\begin{cases}...\end{cases}`, `\begin{aligned}...\end{aligned}`
- `\cancel`, `\textcolor` (stripped, content preserved)

Fallback: `--skip-mathml` flag converts formulas to plain-text brackets `[...]`.

### Code Blocks → Images

Code blocks with syntax highlighting are rendered as images via Pygments, sized for e-reader screens. This avoids font/spacing issues with raw code on Kindle.

### Images

- Remote images auto-downloaded and embedded
- GIF/WebP/BMP → PNG conversion
- PDF figures → PNG (via pymupdf, for arXiv TeX source pipeline)

### Table of Contents

Heading hierarchy (`#`/`##`/`###`) is automatically parsed into a navigable TOC with anchor IDs.

---

## Skills (AI Agent Workflows)

Reusable skill modules that provide structured, multi-step workflows for AI agents:

### 1. `tex_to_kindle` — arXiv TeX Source → KFX

Full pipeline for converting arXiv paper **TeX source** to a Kindle-ready KFX with AI-generated Chinese reading guide:

- Multi-file `\input{}` resolution, custom macro expansion (`\newcommand`, `\def`)
- Math environments → `$$...$$` (preserved as LaTeX for MathML)
- PDF figures → PNG (via pymupdf), tables, algorithm blocks, theorem environments
- **Math delimiter validation** before KFX conversion (Step 2.5)
- **AI paper reading guide** (12-section framework in Chinese, prepended to the paper)

```bash
python skills/tex_to_kindle/scripts/tex2md.py \
  --tex-dir /path/to/extracted/tex \
  --output paper.md \
  --title "Paper Title" --author "Authors"
```

### 2. `merge_books` — Bilingual Ebook Merger

Merge Chinese + English versions of the same book into an **interleaved bilingual format** — Chinese paragraph first with vocabulary annotations, then English paragraph with inline glosses.

- EPUB structure analysis + chapter extraction (handles split chapters, non-standard numbering)
- Semantic paragraph alignment (not mechanical line-matching)
- **Vocabulary annotations**: CET-4+ words annotated in Chinese section, CET-6+ in English section
- Parallel chapter processing via subagents (up to 3 concurrent)
- Currency `$` → `USD($)` convention to prevent MathML conflicts
- Per-chapter KFX conversion + batch push to Kindle

```bash
# Analyze EPUB structure
python skills/merge_books/scripts/analyze_epub.py --en english.epub --zh chinese.epub

# Extract chapters
python skills/merge_books/scripts/extract_chapters.py \
  --en english.epub --zh chinese.epub --out book_dir

# Merge final output
python skills/merge_books/scripts/merge_md.py --dir book_dir/markdown --title "书名"
```

### 3. Troubleshooting Tools

#### 3.1 `md-math-check` — Math Delimiter Validator

Universal pre-conversion check for **any** Markdown file. Detects and helps fix `$`/`$$` pairing issues that produce garbage MathML and crash KFX conversion.

```bash
python scripts/check_math_delimiters.py input.md
```

Outputs JSON report with issue types, line numbers, and fix suggestions:
- `ODD_DD_COUNT` / `ODD_D_COUNT` — unpaired delimiters
- `STRAY_DD` — mid-line `$$` (likely typo for `$`)
- `MISPAIRED_DD` — `$$` pair containing headings/prose (not math)
- `EMPTY_DD_PAIR` — `$$` immediately followed by `$$`

The AI agent reads the report, fixes the Markdown, then re-checks until clean. Works for arXiv, Zhihu, WeChat — any source.

#### 3.2 `fix_tokindle` — KFX Conversion Debugger

When KFX conversion fails with *"Kindle conversion has encountered an internal error"*, this skill provides:
- Pipeline overview (MD → HTML → EPUB → KFX)
- Known failure points catalog (FP1–FP6b)
- Diagnostic methods (EPUB XHTML inspection, formula tracing, verbose logs)
- Binary-search strategy for isolating problematic content

---

## Installation

### Prerequisites

| Component | Required For | Notes |
|-----------|-------------|-------|
| Python 3.8+ | All features | |
| `pip install -r requirements.txt` | All features | markdown, bs4, latex2mathml, EbookLib, etc. |
| [Calibre](https://calibre-ebook.com/download) | KFX output | `ebook-convert` command |
| [Kindle Previewer 3](https://www.amazon.com/Kindle-Previewer/b?ie=UTF8&node=21381691011) | KFX output | KFX rendering engine |
| [KFX Output plugin](https://www.mobileread.com/forums/showthread.php?t=291290) | KFX output | Calibre plugin |
| [pymupdf](https://pypi.org/project/PyMuPDF/) | arXiv TeX source | PDF figure → PNG |
| [Playwright](https://playwright.dev/) | Browser-mode downloads | Optional |

> **EPUB-only users** (Kobo, Boox, etc.): skip Calibre / Kindle Previewer / KFX plugin.

### Quick Setup

```bash
git clone https://github.com/ia-xu/SendArticle2Kindle.git
cd SendArticle2Kindle
pip install -r requirements.txt

# For KFX (Kindle users):
#   1. Install Calibre: https://calibre-ebook.com/download
#   2. Install Kindle Previewer 3
#   3. Install KFX Output plugin in Calibre

# For arXiv TeX source:
pip install pymupdf
```

---

## Web UI

A Flask web interface is available for manual operation — paste URLs, upload files, and push to your e-reader without an AI agent.

![Web UI](articles/img.png)

```bash
python webui/app.py
# Open http://127.0.0.1:5006
```

📖 **项目介绍（知乎）**: [网络文章转 Kindle 电子书工具](https://zhuanlan.zhihu.com/p/2019355339670189711)

For detailed Web UI and CLI usage (cookie setup, browser mode, batch operations), see [`README_v0.1.0.md`](README_v0.1.0.md).

---

## Project Structure

```
SendArticle2Kindle/
├── mcp_server.py              # MCP server entry point
├── src/
│   ├── md2kfx.py              # MD → EPUB → KFX core converter
│   ├── downloader/            # Article downloaders
│   │   ├── zhihu2markdown.py
│   │   ├── wechat2markdown.py
│   │   └── arxiv2markdown.py
│   ├── config.py              # Configuration
│   └── tools/                 # Database, Kindle device, file management
├── scripts/
│   └── check_math_delimiters.py  # $ delimiter validator
├── skills/                    # AI agent workflow modules
│   ├── tex_to_kindle/         # arXiv TeX → KFX (tex2md.py + paper reading guide)
│   ├── merge_books/           # Bilingual ebook merger (EPUB analysis + chapter alignment)
│   ├── md-math-check/         # Math delimiter checker
│   └── fix_tokindle/          # KFX debug & fix guide
├── webui/                     # Flask web interface
├── outputs/                   # Conversion output directory
├── requirements.txt
└── README.md                  # This file
```

---

## License

MIT
