---
name: tex_to_kindle
description: >
  Convert arXiv TeX source to Kindle KFX. Handles multi-file LaTeX projects,
  custom macros, math formulas, PDF figures, TikZ/pgfplots figures,
  tables, algorithm blocks, and code listings.
  v4.2: P45-P47 — tildes (~) in prose not converted to space; standalone
  multi-panel figures need varwidth (not plain \\ row breaks); algorithm2e
  \Return trailing content causes odd $ count after image replacement.
  v4.1: P39-P44 — multi-panel minipage figures lose all but the first chart,
  tabularx tables leak raw content, algorithm2e blocks leak, @{} mangled in
  tabular specs, \newcolumntype dropped, \eqref eats first label char.
  v4.0: P35-P38 — TikZ figures silently dropped (figure envs with TIKZ placeholders,
  section-file misdetection, dir/file collision on \input, caption math mangling).
  v3.7: P27 — MCP server image path mismatch (images copied to {id}_images/ but looked up in images/).
version: 4.2.0
author: Hermes Agent
platforms: [windows]
metadata:
  hermes:
    tags: [arxiv, tex, latex, kindle, kfx, academic, papers, tikz, miktex]
---

# TeX Source → Kindle KFX (v4.2)

**v4.1:** Multi-panel figures built from `\begin{minipage}` × N `\includegraphics`
keep only the FIRST chart — rebuild as a standalone composite (P39, Step 3d).
`tabularx` tables are not captured as TABLE_RAW and leak raw column specs into
prose — rebuild as a Markdown table from source (P40). `algorithm2e` blocks leak
`\KwIn`/`\KwOut`/`\DontPrintSemicolon` — compile standalone → PNG (P41, Step 3e).
Orphan-brace cleanup mangles `@{}` → `@` in TABLE_RAW tabular specs and leaves a
`[tp]` line from `\begin{table}[tp]` (P42). `\newcolumntype` defined before
`\begin{table}` is dropped → `P{}`/`L{}` undefined in table_renderer (P43).
`\eqref{eq:x}` drops the FIRST character of the label (`(Equation atentmoe)`) —
build a label→number map from source with `scripts/build_eq_map.py` (P44).

**v4.0:** TikZ figures were silently dropped from output — see P35-P38.
- P35: figure envs containing `<!-- TIKZ_FIGURE:... -->` placeholders returned `''`,
  deleting the whole figure (image + caption + label).
- P36: `_is_tikz_figure` misclassified section files containing any tikzpicture as
  standalone figure files (whole section replaced by one placeholder).
- P37: `resolve_input` used `exists()`, so a directory named like the file
  (`appendix/` vs `appendix.tex`) shadowed it — the whole appendix was lost.
- P38: `_clean_text_content` mangled `$...$` math in captions into stray `$$`,
  corrupting global `$$` pairing and leaving `\subsection` headings unconverted.
Also: `\ref{fig:x}` → `(Figure N)` via label→number map; inline tikzpictures in
figure envs → `<!-- TIKZ_RAW:N -->` blocks compiled by tikz_placeholder.py Phase 3;
`\S`→`§`, `~(`→` (`, `\printbibliography` stripped. Full diagnostic workflow:
`references/tikz-figure-loss-debugging.md`.

**v3.9:** P32: `\\[2pt]` line break misidentified as `\[` display math (negative lookbehind fix).
P33: `\iffalse...\fi` conditional compilation blocks not stripped. USD($) masking rule in
quality checks (mask, never replace — it is an intentional md2kfx escape token).

**v3.7:** P27: MCP server image path mismatch (images → `{id}_images/` not `images/`).

**v3.3.1:** `\r\n` Windows line-ending fix in `table_renderer.py` and `code_renderer.py`
(`\n` → `[\r\n]+` in TABLE_RAW/CODE_RAW block regex) — see P24.

**v3.3 changes:** `\\bm` single-char fix, `\\USD($)$` recovery, color macro stripping
(`\brickred`/`\midnightblue`/`\white`), `{width=}` orphan cleanup, code-listing→image
workflow (Step 3c), triple-backtick prose pitfall (P19), math-nesting fix (P21),
`&`→`\qquad` in md2kfx.py (P23).

## Prerequisites

- **MiKTeX** at `D:\storage\program\miktex\`:
  `pdflatex.exe` at `D:\storage\program\miktex\miktex\bin\x64\pdflatex.exe`

- **Python** (tokindle conda env):
  `D:\storage\program\miniconda\envs\anxu\python.exe`
  Required: `pymupdf` (fitz) for PDF→PNG conversion.

- **tokindle MCP server** running (for KFX conversion + push)

- **Kindle** connected via USB

### Script paths

| Script | Path |
|--------|------|
| tex2md.py | skill scripts dir (`scripts/tex2md.py`) |
| tikz_placeholder.py | skill scripts dir (`scripts/tikz_placeholder.py`) |
| table_renderer.py | skill scripts dir (`scripts/table_renderer.py`) |
| extract_formulas.py | skill scripts dir (`scripts/extract_formulas.py`) |
| build_eq_map.py | skill scripts dir (`scripts/build_eq_map.py`) |
| md2kfx.py | `D:/data/anan/projects/tokindle/src/md2kfx.py` |

### Python

All scripts use the tokindle conda env:
```
PYTHON="D:/storage/program/miniconda/envs/anxu/python.exe"
```

## Workflow (7 Steps)

### Step 1: Download & Extract TeX Source

```bash
PAPER_ID="2510.26692"
OUTPUT_DIR="D:/data/anan/projects/tokindle/output"

curl -L -o "/tmp/arxiv-${PAPER_ID}.tar.gz" "https://arxiv.org/src/${PAPER_ID}"
mkdir -p "/tmp/arxiv-${PAPER_ID}"
tar xzf "/tmp/arxiv-${PAPER_ID}.tar.gz" -C "/tmp/arxiv-${PAPER_ID}"
```

If the user provides a local tar.gz or already-extracted directory, skip download.

### Step 2: TeX → Markdown (basic conversion)

```bash
PYTHON="D:/storage/program/miniconda/envs/anxu/python.exe"
TEX2MD="<skill_dir>/scripts/tex2md.py"

"$PYTHON" "$TEX2MD" \
  --tex-dir "/tmp/arxiv-2510.26692" \
  --output "D:/data/anan/projects/tokindle/output/paper.md" \
  --title "Paper Title" \
  --author "Author Names"
```

**What tex2md.py handles:**
- Multi-file projects via `\input{}` resolution (comments stripped first)
- **TikZ/pgfplots detection**: files containing `\begin{tikzpicture}`,
  `\begin{axis}`, or `\pgfdeclareplotmark` → `<!-- TIKZ_FIGURE:path -->`
- Custom macro expansion (`\newcommand`, `\def`)
- Math environments → `$$...$$` (preserves LaTeX as-is for latex2mathml)
- `\ensuremath{...}` → `$...$`
- Figures: `\includegraphics` → PNG (PDF→PNG via pymupdf)
- Tables: `tabular` → Markdown tables
- Algorithm blocks → code blocks
- Lists: `itemize`/`enumerate` → Markdown lists
- Citations: `\cite` → `[key]`, references: `\ref{fig:x}` → `(Figure N)` (label→number map recorded during figure conversion; non-figure labels keep the `(label)` fallback)

**What tex2md.py v3.3 handles (formerly LLM tasks):**
- `\operatorname`→`\mathrm`, `\bm{...}`→`\boldsymbol{...}`, `\bm x`→`\boldsymbol{x}` (single-char, P20), `\tag{...}` removal
- `\textcolor`, `\colorbox`, `\raisebox` → content only
- `\faGithub`, `\faEnvelopeO` removal + orphan brace cleanup
- `\parencite{...}`→`[...]`, `\url{...}`→URL
- `\subparagraph{...}`→`##### ...`
- `\cmidrule`, `\newenvironment`, `\captionsetup` removal
- Leaked formula `$$` wrapping (`_wrap_leaked_math_blocks`)
- `\USD($)$` → `$$` recovery (P18 root cause 1)
- Custom color macros: `\brickred{...}`, `\midnightblue{...}`, `\white{...}` → content
- Orphan `{width=...}` blocks from `\includegraphics` options

**Post-Processing Checklist (LLM — run after Step 3c):**

After all renderers complete, fix remaining issues using **terminal-started
Python scripts** (NOT execute_code's write_file — see P10). Write each fix
script with `write_file`, run it with `terminal`, and have it use Python's
`open()` to read/write the MD file directly.

Common fix patterns (use str.replace or re.sub in the terminal script):

```python
with open("paper.md", "r") as f: content = f.read()
import re

# Triple ``` in prose → md2kfx code fence eats image refs
content = content.replace("```<PUSH>`", "`<PUSH>`")
content = content.replace("```<POP>`", "`<POP>`")

# \USD($)$ → $$ (corrupts $$ pairing)
content = content.replace(r'\USD($)$', '$$')

# Table cell $$ mangling ($\phi$/$\downarrow$ → $$)
content = re.sub(r'\| \{r+\w*\} \|  \| Training PPL \(\$\$\)',
    r'|  |  | Training PPL ($\\downarrow$)', content)

# Orphan {width=...} from includegraphics options
content = re.sub(r'\{width=1\\\\columnwidth,?\s*center\}', '', content)
content = re.sub(r'\{width=1\\\\columnwidth\}', '', content)

# Custom color macros not expanded
for cmd in ['brickred','midnightblue','white','kimiblue']:
    content = re.sub(r'\\'+cmd+r'\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',r'\1',content)

# \bm x single-char (no braces) → \boldsymbol{x}
content = re.sub(r'\\bm\s+([a-zA-Z])', r'\\boldsymbol{\1}', content)

# {python} code block → ```python
content = content.replace('\n{python}\n', '\n```python\n')

# $...$$...$ nested math → $$...$$
content = re.sub(r'\$\n\$\$\n(.*?)\n\$\$\n\$', r'$$\n\1\n$$', content, flags=re.DOTALL)

# Convert ~ (non-breaking space) to regular space in PROSE only
# Must split by $$ to avoid touching math regions
parts = content.split('$$')
for i in range(0, len(parts), 2):  # even indices = prose
    parts[i] = parts[i].replace('~', ' ')
content = '$$'.join(parts)

# Verify $$ pairing (mask USD($) first — see P34)
usd_masked = content.replace('USD($)', 'XXXXX')
dd = usd_masked.count('$$')
print(f"$$: {dd} {'OK' if dd%2==0 else '⚠️ ODD — use P18 stack matching'}")

with open("paper.md","w") as f: f.write(content)
```

Also verify: 0 `TABLE_RAW`, 0 `CODE_RAW`, 0 `TIKZ_FIGURE` remaining;
image ref count matches expected. Run `check_math_delimiters.py` from the
`fix_tokindle` skill (ignore `MISPAIRED_DD` warnings for long formulas —
only `ODD_DD_COUNT` and `STRAY_DD` are real problems).

## Design Philosophy (v3.5)

### Step 3b: Render Complex Tables as Images (v3.2)

tex2md.py v3.2 emits `<!-- TABLE_RAW:N|caption -->` blocks for tables
with complex column specs (`@{}`, `>{}`, `!{}`). These tables cannot be
converted to Markdown and are rendered as PNG images.

```bash
PYTHON="D:/storage/program/miniconda/envs/anxu/python.exe"
TABLE_RENDERER="<skill_dir>/scripts/table_renderer.py"

"$PYTHON" "$TABLE_RENDERER" \
  "D:/data/anan/projects/tokindle/output/paper.md" \
  --tex-dir "/tmp/arxiv-2510.26692" \
  --dpi 200
```

This script:
1. Scans for `<!-- TABLE_RAW:N|caption -->...<!-- /TABLE_RAW:N -->` blocks
2. Restores escaped LaTeX commands (`\LATEXBS` → `\`)
3. Wraps each table in a standalone document with proper preamble
   (booktabs, multirow, colortbl, xcolor, etc.)
4. Compiles with pdflatex, converts PDF → PNG
5. Replaces blocks with `![caption](images/table_N.png)`

**Custom colors/commands in tables:** The preamble in table_renderer.py
includes common colors from Kimi Linear and similar papers. If the paper
uses additional custom commands in tables, add them to `TABLE_PREAMBLE`
in table_renderer.py before running.

### Step 3c: Render Code Listings as Images (v3.2)

tex2md.py emits `<!-- CODE_RAW:N|caption -->` blocks for figure environments
that contain `minted`/`lstlisting`/`verbatim` code instead of images.
These cannot be converted to Markdown and are rendered as PNG images.

```bash
PYTHON="D:/storage/program/miniconda/envs/anxu/python.exe"
CODE_RENDERER="<skill_dir>/scripts/code_renderer.py"

"$PYTHON" "$CODE_RENDERER" \
  "D:/data/anan/projects/tokindle/output/paper.md" \
  --dpi 150
```

This script:
1. Scans for `<!-- CODE_RAW:N|caption -->...<!-- /CODE_RAW:N -->` blocks
2. Restores escaped LaTeX commands (`\LATEXBS` → `\`)
3. Wraps in a standalone document with minted/tcolorbox/xcolor preamble
4. Compiles with pdflatex `--shell-escape` (required for minted), converts PDF → PNG
5. Replaces blocks with `![caption](images/code_N.png)`

**Requirements:** MiKTeX with `minted` package + Python `pygments` installed.

### Step 3d: Rebuild Multi-Panel Figures (v4.1)

Multi-panel figures (2×2 minipage grids, subfigure arrays) only keep the first
panel after tex2md (P39). Rebuild the full composite:

**IMPORTANT — use `varwidth`, not plain standalone:** Plain `\documentclass{standalone}`
does not honor `\\` row breaks between minipage rows — all panels end up on one
row (too wide). See P46 for the full working template with `varwidth`.

```bash
# figure13.tex — replicate original minipage layout with ABSOLUTE pdf paths
# (relative paths render as literal file-path text — verify with vision!)
# 4 x \begin{minipage}{0.24\textwidth} ... \includegraphics[width=\textwidth]{ABS/path.pdf}\\[2pt] {\small (a) Label} ...
# rows joined by \\[8pt]
pdflatex -interaction=nonstopmode figure13.tex
python -c "import fitz; d=fitz.open('figure13.pdf'); p=d[0]; p.get_pixmap(dpi=200).save('../images/figure13_composite.png')"
```

Then replace the single-panel `![...](images/panel_a.png)` ref with the composite.

### Step 3e: Render Algorithm Blocks as Images (v4.1)

`algorithm2e` blocks leak raw `\KwIn`/`\KwOut` (P41). Wrap in a standalone doc:

```latex
\documentclass[border=8pt]{standalone}
\usepackage{amsmath,amssymb,amsfonts,bm}
\usepackage[ruled,linesnumbered]{algorithm2e}
\IncMargin{1.5em}
\begin{document}
\begin{algorithm}[H] ... \end{algorithm}
\end{document}
```

Compile + convert (same as 3d), replace the raw block with `![caption](images/alg_N.png)`.

### Step 3: Resolve TikZ Placeholders with MiKTeX

```bash
PYTHON="D:/storage/program/miniconda/envs/anxu/python.exe"
TIKZ_PH="<skill_dir>/scripts/tikz_placeholder.py"

"$PYTHON" "$TIKZ_PH" \
  "D:/data/anan/projects/tokindle/output/paper.md" \
  --tex-dir "/tmp/arxiv-2510.26692" \
  --dpi 200
```

This script:
1. Scans for `<!-- TIKZ_FIGURE:path -->` placeholders (TikZ files `\input`ed inside figure envs)
2. Wraps each .tex in a standalone document, compiles with MiKTeX pdflatex,
   converts PDF → PNG via pymupdf
3. Replaces placeholders with `![name](images/name.png)`
4. Also handles `<!-- MISSING_IMAGE:path -->` — second-attempt image resolution
5. Phase 3 (v4.0): `<!-- TIKZ_RAW:N|caption -->...<!-- /TIKZ_RAW:N -->` blocks —
   inline `\begin{tikzpicture}` directly inside a figure env (no `\input`) — compiled
   the same way and replaced with `![caption](images/tikz_N.png)`

MiKTeX auto-installs missing packages on first run (2-5 min). Subsequent runs are fast.

**IMPORTANT — Custom preamble:** Before running, check the paper's main.tex for custom
`\definecolor{...}` and `\usetikzlibrary{...}` entries. If present, read
`tikz_placeholder.py` and add them to the `TIKZ_PREAMBLE` variable. See Pitfall P3.

### Step 4: LLM Agent Post-Processing

tex2md.py v3.2 handles the bulk of deterministic conversions.
LLM post-processing uses `extract_formulas.py` for systematic review.

**4a. Extract formula index (run first):**

```bash
"$PYTHON" "<skill_dir>/scripts/extract_formulas.py" \
  "D:/data/anan/projects/tokindle/output/paper.md" \
  --output "D:/data/anan/projects/tokindle/output/paper_formulas.txt"
```

This produces a numbered index of all $$...$$ blocks (B1, B2, ...) and
$...$ inline formulas (I1, I2, ...) with auto-detected issues (unbalanced
braces, unsupported commands).

**4b. Read the formula index and fix issues:**

Read `paper_formulas.txt`. Look for:
- `UNBALANCED BRACES` — fix with `patch` on the original MD
- Formulas that look like prose wrapped in `$$` — unwrap them
- Formulas with `\operatorname`, `\bm{`, `\textcolor` — should be fixed
  by tex2md.py now, but verify

For each issue found, note the formula ID and the original MD line numbers,
then use `patch` to fix the original `paper.md` file.

**4c. Verify with the scan script (MASK `USD($)` first — see P34):**

```python
# In execute_code:
import re
PATH = "<output_dir>/paper.md"
with open(PATH, 'r', encoding='utf-8') as f:
    content = f.read()
# CRITICAL: mask USD($) before counting — its internal $ is not a delimiter
masked = content.replace('USD($)', 'XXXXX')
dd = masked.count('$$')
sd = masked.count('$') - dd * 2
print(f"$$: {dd} ({'EVEN' if dd % 2 == 0 else 'ODD'})")
print(f"$: {sd} ({'EVEN' if sd % 2 == 0 else 'ODD'})")
```

### Step 5: Quality Check (MANDATORY before KFX)

Before generating the reading guide or converting to KFX, run a quality scan
to catch any remaining conversion issues. Use `execute_code` with Python
(not repeated `patch` calls — `execute_code` is much faster for bulk fixes).

**Scan for:**
- $$ / $ counts (must be even)
- Remaining LaTeX commands outside math blocks
- Orphan `{` / `}` in prose
- Image reference validity
- Section completeness (all expected sections present)

**Common fix patterns (use execute_code for bulk):**
- `\operatorname`→`\mathrm`, `\bm{`→`\boldsymbol{` (should be handled by tex2md.py now)
- `\textcolor{color}{content}` → `content` (balanced-brace stripping)
- `\raisebox` remnants + orphan `{dimen{...}}` patterns
- `\parencite{key}` → `[key]` for any missed by tex2md.py
- Contiguous raw-math lines → wrap in `$$...$$`
- Stray `\item` → `- `

The reading guide (Step 6) can be deferred — prioritize getting a clean,
conversion-ready MD file first. The user may want to review the conversion
quality before adding the guide.

### Step 6: Generate AI Paper Reading Guide (optional, deferrable)

Use a subagent to read the full Markdown and generate a structured 12-section
reading guide IN CHINESE (中文), then prepend it.

```
delegate_task(
  goal="Read a paper Markdown file, write a 12-section reading guide IN CHINESE, and prepend it to the file",
  context="""
    Paper MD path: <path to paper_name.md>
    Template: <skill_dir>/templates/paper_analysis.md

    Read the template file first for the full 12-section framework and writing rules.
    Then read the paper MD file completely.
    Write the guide following ALL 12 sections and ALL writing rules from the template.

    LANGUAGE RULES (CRITICAL):
    - 导读正文用中文撰写。
    - 数学公式保持 LaTeX 不翻译（$...$, $$...$$）。
    - 专有名词首次出现时附英文原文，如：重要性采样(importance sampling)。
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

### Step 7: Convert Markdown → KFX

**If Kindle shows image placeholders after conversion**, see P27 and
`references/md2kfx_image_handling.md` for the diagnostic workflow.

**Via tokindle MCP (recommended):**
```
mcp_tokindle_upload_local_file(
    file_path="D:/data/anan/projects/tokindle/output/paper.md",
    title="Paper Title",
    author="Author Names"
)
# Wait 2-4 min, then poll:
mcp_tokindle_get_file_info(file_id="...")
# When status="converted" and has_kfx=true:
mcp_tokindle_send_to_kindle(file_id="...")
```

**Direct md2kfx.py (when MCP is unavailable):**
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

## Math Formula Strategy

TeX math is preserved as LaTeX (`$...$` / `$$...$$`) — NOT converted to Unicode.
The md2kfx.py pipeline uses `latex2mathml` to convert LaTeX → MathML → KFX.

tex2md.py v3.2 handles deterministic conversions (`\operatorname`, `\bm`,
`\textcolor`, etc.) in `_process_math()` and `_cleanup()`. Structural issues
(alignment wrapping, $$ pairing) remain for LLM Step 4.

## Pitfalls

Quick reference — items marked ★ have detail blocks below; everything else is
already fixed in the scripts (symptom → fix).

| # | Issue | Symptom | Fix |
|---|-------|---------|-----|
| P1 | pymupdf missing | PDF→PNG fails | `pip install pymupdf` (anxu env) |
| P2 | MiKTeX path | tikz/table compile fails | pdflatex at `D:\storage\program\miktex\miktex\bin\x64\` |
| P3 | custom colors/tikz libs | undefined color/library | add to `TIKZ_PREAMBLE` before Step 3 |
| P4 | wrapper envs | standalone compile fails | auto-stripped by tikz_placeholder |
| P5 | nested-brace captions | caption mis-extracted | balanced-brace matching |
| P6 | MiKTeX auto-install | first compile slow | wait 2-5 min |
| P7 | KFX MathML limit | KFX fails, EPUB ok | push EPUB or split at section boundary |
| P8 | multi-file projects | missing sections | `\input`/`\include` both resolved |
| P9 | complex custom macros | unexpanded commands | fix in Step 4 |
| P10★ | read_file→write_file | line numbers written back, file corrupt | terminal + standalone Python script only |
| P11 | patch splits signatures | SyntaxError | py_compile after any .py edit |
| P12 | stray `\parencite` | citation becomes text | handled by tex2md |
| P13 | leaked align* formulas | math without `$$` | `_wrap_leaked_math_blocks` |
| P14 | complex tables | can't be Markdown | `TABLE_RAW` → table_renderer PNG |
| P15 | regex `\|` alternation | matches everything | references/regex-pitfalls.md |
| P16 | non-raw re.escape | `\r` treated as CR | always raw strings |
| P17 | raisebox in footnotes | orphan `{0pt{...}}` | `_clean_orphan_dimen_braces` |
| P18★ | odd `$$` cascade | one stray `$$` corrupts all pairing | stack-match first orphan; fix root cause only |
| P19 | stray ``` in prose | code_to_image eats content | replace with single backtick before KFX |
| P20 | `\bm x` single char | not bolded | handled by tex2md |
| P21 | `$...$$...$` nesting | invalid markup | keep inner `$$` only |
| P22 | figure+subfigure+minted | listing lost | render listing standalone with minted |
| P23 | `&` alignment chars | literal & on Kindle | md2kfx replaces with `\qquad` |
| P24 | `\r\n` line endings | renderers find 0 blocks | regex uses `[\r\n]+` |
| P25 | — | — | removed (image format not root cause) |
| P26★ | patch tool corrupts `\r` | `\right)` → `\r\night)` | never patch LaTeX content; use Python scripts |
| P27★ | MCP image path mismatch | placeholders on Kindle | fixed in mcp_server.py; verify KFX >2MB |
| P30★ | guide introduces bare `$` | KPR internal error | re-scan `$` pairing after Step 6 |
| P31★ | giant MathML | KFX internal error | no MOBI; push EPUB or AZW3 |
| P32 | `\\[2pt]` vs `\[` | stray `$$2pt]` | negative lookbehind added |
| P33 | `\iffalse...\fi` | dead content leaks | stripped in `_strip_comments` |
| P34 | `USD($)` escape token | pairing checks false-fail | MASK, never replace |
| P35★ | TikZ figure envs dropped | figure+caption+label vanish | v4.0: preserved; inline tikz → TIKZ_RAW |
| P36 | section misdetected as TikZ | whole section replaced | `_is_tikz_figure` rejects `\section` files |
| P37 | `\input` hits a directory | appendix/section lost | `is_file()` + fall through |
| P38★ | caption math mangled | `$\boldsymbol{w}$` → `$$` breaks pairing | `_clean_text_content` protects `$...$` |
| P39★ | multi-panel figure (minipage×N) | only first includegraphics converted | rebuild standalone composite, absolute paths (Step 3d) |
| P40★ | `tabularx`/X-column table | raw tabularx leaks into prose | rebuild as Markdown table from source |
| P41★ | `algorithm2e` block | `\KwIn`/`\KwOut`/`\DontPrintSemicolon` leak | standalone algorithm2e compile → PNG (Step 3e) |
| P42 | `@{}` in TABLE_RAW tabular spec | mangled to `@` (breaks compile); `[tp]` line left from `\begin{table}[tp]` | restore `@{}`, strip `[tp]` line before table_renderer |
| P43 | `\newcolumntype` before `\begin{table}` | P{} / L{} undefined in render | add columntypes to TABLE_PREAMBLE |
| P44★ | `\eqref{eq:x}` eats first label char | `(Equation atentmoe)` for `eq:latentmoe` | build_eq_map.py → `(N)` refs |
| P45 | `~` in prose not converted | `data~\cite{key}` → literal `~` in Kindle text | mask `$$`-math regions, replace `~`→space in prose only |
| P46★ | standalone multi-panel fails | `\documentclass{standalone}` + minipage `\\` → all N panels on ONE row | use `varwidth` wrapper with `\vspace` between rows (Step 3d) |
| P47 | algorithm2e `\Return` trailing content | image ref followed by `$ with $x_{i,j}=1$...` → odd `$` count | clean everything after `![...](images/alg_N.png)` to next blank line |

---

### P10: never read_file→write_file MD files ★

`read_file` returns line-numbered content; writing it back (directly or via
execute_code's hermes_tools) corrupts the file. For programmatic MD edits:
write a fix script with `write_file`, run it with `terminal`, use Python
`open()` directly.

### P18: odd $$ count — cascade debugging ★

Stack-match `$$` to locate the FIRST orphan; fix only the root cause and the
cascade resolves. Known root causes: `\USD($)$` → `$$`; `$$` in table cells →
`↓` / `$\downarrow$`; orphan from aligned unwrap. `check_math_delimiters.py`:
only `ODD_DD_COUNT` / `STRAY_DD` / `ODD_D_COUNT` matter — `MISPAIRED_DD` on
long formulas is a false alarm.

### P26: patch tool corrupts `\r` on Windows ★

`\r` inside `\right)`, `\raisebox`, `\ref`, `\rm`... is interpreted as a CR
byte, splitting text (`\right)` → `\r\night)`). Never use the `patch` tool on
LaTeX content — write a standalone Python script (`open().read/replace/write`).
Detect: count `ight)` occurrences (each is a broken `\right)`).

### P27: MCP server image path mismatch ★

mcp_server copied images to `{file_id}_images/` but MarkdownToKFX reads
`images/` — images silently skipped (small KFX, placeholders on Kindle).
Fixed: dest = `UPLOAD_FOLDER/'images'`. Verify: KFX > 2MB, images in EPUB zip.
Full workflow: references/md2kfx_image_handling.md.

### P30+P31: bare `$` from reading guide / giant MathML ★

Step 6 guide may add currency `$2.03` → bare `$` breaks pairing → latex2mathml
emits 10-34K-char MathML → KPR "internal error". After Step 6 re-run the `$`
stack check; convert `$digit` → `USD($)digit`. Template forbids bare `$`.
Do NOT use MOBI (strips MathML) — push EPUB or AZW3.

### P35: figure envs with TikZ placeholders dropped (v4.0) ★

`resolve_input` turns `\input{figures/xxx.tex}` into `<!-- TIKZ_FIGURE:path -->`;
`_convert_figure_env` then found no `\includegraphics` and returned `''` —
deleting placeholder, caption AND `\label` in one shot. **Symptoms:**
`\ref{fig:arch}` → `(Figure arch)` fallback; figure never appears; no
TIKZ_FIGURE placeholders survive. **Fix:** detect the placeholder inside
`inner`, increment `figure_counter`, record the label in `figure_labels`, emit
placeholder + `*Figure N: caption*`. Inline `\begin{tikzpicture}` (no `\input`)
→ `TIKZ_RAW` block → tikz_placeholder Phase 3 renders `images/tikz_N.png`.
Verify: 0 leftover TIKZ_FIGURE/TIKZ_RAW; every `\ref{fig:x}` → `(Figure N)`.

### P36: section files misclassified as TikZ (v4.0)

`_is_tikz_figure` matched any file containing a tikzpicture — a section file
with one inline figure (e.g. `5-infrastructure.tex`) was replaced by one
placeholder, wiping the whole section. **Fix:** reject files containing
`\section`/`\subsection`/`\subsubsection`/`\chapter`/`\part`/`\begin{document}`/
`\documentclass`/`\include{`.

### P37: directory shadows file in resolve_input (v4.0)

`\input{appendix}` matched the `appendix/` dir (`exists()` True) → read failed →
`% [Could not read]` → whole appendix lost. **Fix:** `is_file()` +
`except: continue`. **Symptom:** `# Appendix` heading but no appendix content.

### P38: caption math mangled into stray `$$` (v4.0) ★

`_clean_text_content` stripped commands INSIDE `$...$` (`($\boldsymbol{w}$)` →
`($$)`) → stray `$$` corrupted `_protect_math`'s DOTALL `$$...$$` matching —
everything up to the next real `$$` (including `\subsection{...}` headings) was
swallowed raw. **Fix:** protect `$$...$$`/`$...$` with `__MATHCLEAN{n}__`
before stripping commands, restore after. **Symptoms:** raw `\subsection{...}`
in MD, `($$)` in captions, odd `$$` count.

### P39: multi-panel minipage figures (v4.1) ★

Figure envs with `\begin{minipage}{0.48\textwidth}` × N `\includegraphics`
(2×2 benchmark grids, subfigure panels) — tex2md only converts the FIRST
includegraphics; the rest are silently dropped. Only the first PDF→PNG appears
in `images/`. **Detect:** figure caption names N benchmarks but only 1 image
ref exists. **Fix (Step 3d):** write a standalone `.tex` replicating the
minipage layout (4 panels, `\\[8pt]` row gap, `(a)-(d)` small labels), compile
with pdflatex, convert PDF→PNG, replace the single-panel ref. Use ABSOLUTE PDF
paths — relative paths silently render as literal file-path text (verify with
vision!). Verify: `grep -oE '!\[[^]]*\]\(images/[^)]+\)'` counts match figure count.

### P40: tabularx tables leak (v4.1) ★

Tables using `tabularx` (X column) are NOT emitted as TABLE_RAW — tex2md only
handles `tabular`. Symptom: `*caption*` italic line followed by raw
`{0.94\linewidth}{ >{\raggedright\arraybackslash}X ... }` column spec and
` & cell` rows in prose. **Fix:** rebuild as a Markdown table from the source
.tex (read the rows, transpose `&`-separated cells), keep the caption, map the
`tab:` label to its real number by document order.

### P41: algorithm2e blocks leak (v4.1) ★

`\begin{algorithm}` envs are NOT captured as CODE_RAW — raw `\KwIn`, `\KwOut`,
`\For{...}`, `\DontPrintSemicolon`, `\Return{...}` leak into prose. **Fix
(Step 3e):** wrap the algorithm body in a standalone doc with
`\usepackage[ruled,linesnumbered]{algorithm2e}` + `\IncMargin{1.5em}` + math
packages, compile with pdflatex, convert to PNG, replace block with
`![caption](images/alg_N.png)`.

### P44: \eqref eats first label char (v4.1) ★

`\eqref{eq:latentmoe}` → `(Equation atentmoe)` — first char of label dropped
(`latentmoe`→`atentmoe`, `qb-update`→`b-update`, `kcp-compose`→`cp-compose`,
`moe-routing`→`oe-routing`). **Fix:** run `scripts/build_eq_map.py --tex-dir
<src> --main main.tex` → label→number map (handles `equation`=+1, `align`=one
number per `\\` row unless `\nonumber`, `\[ \]` unnumbered, document order via
`\input` resolution), then replace `(Equation X)` → `(N)` in the MD.

### P45: Tildes (~) in prose not converted to space

tex2md.py does not convert `~` (LaTeX non-breaking space) to regular space
in prose text. These appear pervasively before `\cite{}` calls (`data~\cite{key}`)
and between words. On Kindle they render as literal `~` characters.

**Detect:** `grep -c '~' paper.md` — if count > 10, fix needed.
**Fix (terminal Python script):**
```python
parts = content.split('$$')
for i in range(0, len(parts), 2):  # even indices = prose
    parts[i] = parts[i].replace('~', ' ')
content = '$$'.join(parts)
```
Must mask `$$`-delimited math first — `~` inside math (e.g. `$\tilde{x}$` does
not contain literal `~`, but some math expressions might) should not be touched.

### P46: standalone multi-panel compile needs varwidth ★

Step 3d says "replicate original minipage layout" but `\documentclass{standalone}`
does NOT honor `\\` row breaks or `\begin{figure}` environments correctly:
- Plain standalone + `\\[8pt]` between minipage rows → all N panels on ONE row (too wide)
- `\begin{figure}` inside standalone → produces 2+ pages

**Working approach** — use `varwidth` to get a bounded-width single page:
```latex
\documentclass[border=5pt]{standalone}
\usepackage{graphicx}
\usepackage{varwidth}
\begin{document}
\begin{varwidth}{\linewidth}
\noindent
\begin{minipage}[t]{0.48\linewidth} ... \end{minipage}\hfill
\begin{minipage}[t]{0.48\linewidth} ... \end{minipage}

\vspace{8pt}

\noindent
\begin{minipage}[t]{0.48\linewidth} ... \end{minipage}\hfill
\begin{minipage}[t]{0.48\linewidth} ... \end{minipage}
\end{varwidth}
\end{document}
```
Compile from a dedicated workdir (e.g., `output/texwork/`), NOT `/tmp` — temp
files get cleaned by `rm` commands and MSYS path mapping can cause issues.

### P47: algorithm2e replacement leaves trailing \Return content

When replacing a leaked `algorithm2e` block with an image ref, the `\Return{...}`
statement may have content that extends beyond what the regex captures. The
replacement leaves trailing math/prose (`$ with $x_{i,j}=1$...`) which causes
an odd `$` count.

**Symptom:** After algorithm image replacement, `$` pairing goes ODD.
**Fix:** After replacement, clean everything from the image ref to the next
paragraph break:
```python
content = re.sub(
    r'(!\[...\]\(images/alg_N\.png\)).*',
    r'\1',
    content
)
```
This truncates any trailing content that leaked past the `\Return` statement.

### P25: Removed (v3.6)

Image format (PNG vs JPEG) is not the root cause of Kindle display issues.

### TikZ Placeholder Format

tex2md emits `<!-- TIKZ_FIGURE:figures/x.tex -->` for `\input`'d TikZ files;
tikz_placeholder.py compiles each standalone → `![name](images/name.jpg)`.

### Missing Image Handling

When `\includegraphics{file.pdf}` can't be resolved, a second attempt is made
in Step 3 (searching tex_dir and figures/).
