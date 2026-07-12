---
name: tex_to_kindle
description: >
  Convert arXiv TeX source to Kindle KFX. Handles multi-file LaTeX projects,
  custom macros, math formulas (preserved as LaTeX for latex2mathml), PDF figures
  (converted to PNG via pymupdf), tables, algorithm blocks, and code listings.
  Produces clean Markdown → KFX via md2kfx.py pipeline.
version: 1.0.0
author: Hermes Agent
platforms: [windows]
metadata:
  hermes:
    tags: [arxiv, tex, latex, kindle, kfx, academic, papers]
---

# TeX Source → Kindle KFX (with AI Paper Reading Guide)

Convert arXiv paper TeX source into a Kindle-readable KFX file with an AI-generated
reading guide prepended. The guide follows a 12-section framework that emphasizes
reconstructing the author's thinking path, attacking the paper's assumptions, and
proposing follow-up research — not passive summarization.

Three-stage pipeline:
1. TeX → Markdown (tex2md.py: macro expansion, math preservation, PDF→PNG figures)
2. AI paper analysis (subagent reads MD, writes 12-section guide, prepends to MD)
3. Markdown → KFX (md2kfx.py: latex2mathml → EPUB → Kindle Previewer → KFX)

## Prerequisites

- Python with `pymupdf` (fitz) installed in the tokindle conda env:
  ```
  "D:\storage\program\miniconda\envs\anxu\python.exe" -m pip install pymupdf
  ```
- tokindle MCP server running (for KFX conversion + push)
- Kindle connected via USB
- The tex2md.py script at: `D:/data/anan/projects/tokindle/skills/tex_to_kindle/scripts/tex2md.py`
- The md2kfx.py converter at: `D:/data/anan/projects/tokindle/src/md2kfx.py`

## Workflow

### Step 1: Download & Extract TeX Source

```bash
PAPER_ID="2607.07508"
OUTPUT_DIR="D:/data/anan/projects/tokindle/output"

# Download (URL: https://arxiv.org/src/<paper_id>  →  arXiv-<id>v1.tar.gz)
curl -L -o "/tmp/arxiv-${PAPER_ID}.tar.gz" "https://arxiv.org/src/${PAPER_ID}"

# Extract
mkdir -p "/tmp/arxiv-${PAPER_ID}"
tar xzf "/tmp/arxiv-${PAPER_ID}.tar.gz" -C "/tmp/arxiv-${PAPER_ID}"
```

If the user provides a local tar.gz path (e.g. from browser download), skip
the curl step and extract that file directly.

### Step 2: Convert TeX → Markdown

```bash
PYTHON="D:/storage/program/miniconda/envs/anxu/python.exe"
TEX2MD="D:/data/anan/projects/tokindle/skills/tex_to_kindle/scripts/tex2md.py"

"$PYTHON" "$TEX2MD" \
  --tex-dir "/tmp/arxiv_paper" \
  --output "D:/data/anan/projects/tokindle/output/paper_name.md" \
  --title "Paper Title" \
  --author "Author Names"
```

This produces:
- `paper_name.md` — merged Markdown with all sections, formulas, tables
- `paper_name/images/` — all figures converted from PDF to PNG

**What tex2md.py handles:**
- Multi-file projects via `\input{}` resolution (comments stripped first)
- Custom macro expansion (`\newcommand`, `\def`) with word-boundary matching
- Math environments → `$$...$$` (equation, align, cases, split preserved as LaTeX)
- `\ensuremath{...}` → `$...$`
- Inline math `$...$` protected during command processing
- Figures: `\includegraphics` → PNG (PDF→PNG via pymupdf, EPS→PNG via PIL)
- Tables: `tabular` → Markdown tables
- Algorithm blocks: `algorithmic` → code blocks
- Lists: `itemize`/`enumerate` → Markdown lists
- Citations: `\cite` → `[key]`
- References: `\ref` → `(Figure/Table label)`
- Special chars: `\%` → `%`, `\$` → `USD($)`

### Step 3: Generate AI Paper Reading Guide

Use a subagent to read the full Markdown and generate a structured 12-section
reading guide IN CHINESE (中文), then prepend it to the file. The subagent keeps
the full paper content out of your context window.

```
delegate_task(
  goal="Read a paper Markdown file, write a 12-section reading guide IN CHINESE, and prepend it to the file",
  context="""
    Paper MD path: <path to paper_name.md>
    Template: D:/data/anan/projects/tokindle/skills/tex_to_kindle/templates/paper_analysis.md

    Read the template file first for the full 12-section framework and writing rules.
    Then read the paper MD file completely.
    Write the guide following ALL 12 sections and ALL writing rules from the template.

    LANGUAGE RULES (CRITICAL):
    - 导读正文用中文撰写。
    - 数学公式保持 LaTeX 不翻译（$...$, $$...$$）。
    - 专有名词首次出现时附英文原文，如：重要性采样(importance sampling)、优势函数(advantage function)。
    - 需要引用论文原文关键句时，用英文引用并加中文解释。
    - 节标题用中文，如"## 1. 研究问题与动机"。
    - 论文原文内容（第二个 --- 之后）保持不动，不做任何修改。

    Use write_file to save the final output (guide + original content) back to the same path.
    Format:
    ---
    [中文导读，12节]
    ---
    [原始论文内容，原封不动]
  """,
  toolsets=["terminal", "file"]
)
```

**The 12 sections** (see template for full spec):
1. 研究问题与动机 (Research problem & motivation)
2. 前人工作及其不足 (Prior work & limitations)
3. **重建作者的思考路径** (Reconstructing the author's thinking path — MOST IMPORTANT)
4. 核心思想精炼 (Core idea distilled)
5. 方法流程与实例 (Method pipeline with example)
6. 数学基础 (Mathematical foundations)
7. 实验设计 (Experimental design — question → setup → answer)
8. 关键收获 (Key takeaways)
9. 最脆弱的假设 (Weakest assumptions)
10. 最小复现 (Minimal reproduction, 1 week)
11. 攻击向量 (Attack vectors)
12. Follow-up 研究方向 (Follow-up research idea)

**Writing style**: Karpathy/He — direct, high information density, no AI-isms.
Each significant claim tagged as [paper], [literature], [inference], or [speculation].

### Step 4: Convert Markdown → KFX

**Option A — Via tokindle MCP (recommended):**
```
mcp_tokindle_upload_local_file(
    file_path="D:/data/anan/projects/tokindle/output/paper_name.md",
    title="Paper Title",
    author="Author Names"
)
# Wait 2-4 min, then poll:
mcp_tokindle_get_file_info(file_id="...")
# When status="converted" and has_kfx=true:
mcp_tokindle_send_to_kindle(file_id="...")
```

**Option B — Direct md2kfx.py (when MCP conversion thread is dead):**
```python
import sys
sys.path.insert(0, "D:/data/anan/projects/tokindle")
from src.md2kfx import MarkdownToKFX

converter = MarkdownToKFX(
    "D:/data/path/to/paper.md",
    "D:/data/path/to/paper.kfx",
    title="Paper Title",
    author="Author Names"
)
result = converter.convert()  # ~3-5 min
```

### Step 5: Verify KFX

Check the KFX file exists and copy to Kindle if not using MCP push:
```bash
ls -la "D:/data/path/to/paper.kfx"
# Copy directly:
cp "D:/data/path/to/paper.kfx" "/f/documents/Downloads/Items01/article/"
```

## Key Design Decisions

### Math Formula Handling

TeX math is preserved as LaTeX (`$...$` / `$$...$$`) — NOT converted to Unicode.
The md2kfx.py pipeline uses `latex2mathml` to convert LaTeX → MathML → KFX.

Supported LaTeX in math regions (kept as-is for latex2mathml):
- `\mathbb{E}`, `\mathcal{D}`, `\mathrm{x}`, `\mathbf{v}`
- `\theta`, `\pi`, `\epsilon`, `\alpha`, etc.
- `\frac{}{}`, `\sum`, `\prod`, `\int`, `\exp`, `\log`
- `\hat{A}`, `\bar{x}`, `\tilde{y}`
- `\begin{cases}...\end{cases}`
- `\text{clip}`, `\left[`, `\right]`

### PDF Figure Conversion

arXiv papers typically have PDF figures. `tex2md.py` uses `pymupdf` (fitz) to
convert each PDF to PNG at 200 DPI. The conversion:
- Takes the first page of each PDF (figures are single-page)
- Outputs to `images/` subdirectory next to the .md file
- md2kfx.py picks up images from this directory during KFX conversion

### Macro Expansion

Custom macros (`\newcommand`, `\def`) are extracted and expanded with
word-boundary matching to prevent false matches (e.g., `\mat` macro must NOT
match `\mathbb`). Macros are expanded BEFORE environment processing.

## Pitfalls

### P1: pymupdf not installed
PDF figures cannot be converted without `pymupdf`. The script will print warnings
and skip figures. Install: `"D:/storage/program/miniconda/envs/anxu/python.exe" -m pip install pymupdf`

### P2: Multi-file project structure
Some papers use `\include` instead of `\input`. The resolver handles both.
If the main file can't be found, it looks for `main.tex`, `0.main.tex`, `paper.tex`.

### P3: Complex custom macros
Macros with optional arguments (e.g., `\newcommand{\stdv}[2][\tiny]{...}`) may
not expand correctly. The extractor captures nargs from `[N]` but doesn't handle
optional argument defaults. Check the output for unexpanded macros.

### P4: BibTeX references
Citations are kept as `[citation_key]` text, not resolved to formatted references.
The bibliography (`\bibliography{}`) is removed. For full references, use the
arXiv HTML version instead.

### P5: md2kfx preprocess_md regex breaks $$ block formulas (FIXED)
md2kfx.py's `preprocess_md` had a regex `(?<!\$)\$\$(?!\$)(?!\s*$)(?!\s*\n)`
intended to fix stray `$$` from Zhihu/WeChat articles. But it matched legitimate
`$$...$$` block formula openers (e.g. `$$\mathbb{E}...`), replacing `$$` with `$`.
This left the closing `$$` orphaned, causing the inline `$...$` regex to match
across paragraph boundaries and wrap ordinary text in garbage MathML.

**Fix applied** (md2kfx.py line ~380): commented out the dangerous regex.
Block formulas are handled correctly by the existing `\$\$(.*?)\$\$` regex.

### P6: md2kfx inline regex crosses block math HTML (FIXED)
md2kfx.py's `process_math_formulas` converts `$$...$$` to HTML first, then runs
`\$([^\$]+)\$` on the entire content. The inline regex could match across
the already-inserted block-level MathML HTML, wrapping ordinary text in MathML.

**Fix applied** (md2kfx.py line ~577): block-level MathML HTML is stashed into
placeholders before inline conversion, then restored after.

### P6: Tables with merged cells
`\multicolumn` and `\multirow` are simplified to their content. Complex table
layouts may not convert cleanly to Markdown tables.

### P7: Debugging tex2md.py and KFX conversion failures
If the converter produces wrong output (exploding file size, corrupted formulas,
duplicated content) or KFX conversion fails with "internal error", see
`references/kfx_root_cause_debugging.md` for the full root-cause analysis of the
md2kfx $$ regex bug — including the binary-search methodology, XHTML inspection
techniques, and the trace scripts used to pinpoint the failure.

## Python Environment

All scripts use the tokindle conda env Python:
```
"D:/storage/program/miniconda/envs/anxu/python.exe"
```

Required packages (all pre-installed in the env):
- `pymupdf` (fitz) — PDF→PNG conversion
- `PIL` (Pillow) — image format conversion
- `requests` — remote image download (not needed for TeX source)
