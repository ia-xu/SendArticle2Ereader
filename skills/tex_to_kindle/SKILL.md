---
name: tex_to_kindle
description: >
  Convert arXiv TeX source to Kindle KFX. Handles multi-file LaTeX projects,
  custom macros, math formulas, PDF figures, TikZ/pgfplots figures,
  tables, algorithm blocks, and code listings.
  v3.7: P27 — MCP server image path mismatch (images copied to {id}_images/ but looked up in images/).
version: 3.7.0
author: Hermes Agent
platforms: [windows]
metadata:
  hermes:
    tags: [arxiv, tex, latex, kindle, kfx, academic, papers, tikz, miktex]
---

# TeX Source → Kindle KFX (v3.7)

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
- Citations: `\cite` → `[key]`, references: `\ref` → labels

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

# Verify $$ pairing
dd = content.count('$$')
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
1. Scans for `<!-- TIKZ_FIGURE:path -->` placeholders
2. Wraps each .tex in a standalone document, compiles with MiKTeX pdflatex,
   converts PDF → PNG via pymupdf
3. Replaces placeholders with `![name](images/name.png)`
4. Also handles `<!-- MISSING_IMAGE:path -->` — second-attempt image resolution

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

**4c. Verify with the scan script:**

```python
# In execute_code:
import re
PATH = "<output_dir>/paper.md"
with open(PATH, 'r', encoding='utf-8') as f:
    content = f.read()
dd = content.count('$$')
sd = content.count('$') - dd * 2
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

### P1: pymupdf not installed
PDF conversion fails without `pymupdf`.
```
"D:/storage/program/miniconda/envs/anxu/python.exe" -m pip install pymupdf
```

### P2: MiKTeX not installed or wrong path
`tikz_placeholder.py` requires `pdflatex.exe` at:
`D:\storage\program\miktex\miktex\bin\x64\pdflatex.exe`

### P3: Custom colors/libraries in paper preamble
If the paper defines custom `\definecolor{...}` or uses TikZ libraries beyond
the defaults, read `tikz_placeholder.py` and add them to the `TIKZ_PREAMBLE`
variable before Step 3. Default included libraries:
`arrows.meta, positioning, calc, shapes.geometric, shapes.misc, shapes.symbols,
decorations.text, decorations.pathreplacing, decorations.pathmorphing,
decorations.shapes, calligraphy, patterns, patterns.meta, fit, backgrounds,
chains, shadows, math, matrix, circuits.ee.IEC, plotmarks`

Default included colors: `brickred, midnightblue, limegreen, salmon, darkcyan, darkgrey, mygrey, kimiblue`

### P4: wrapfigure/subfigure/adjustbox wrappers
`tikz_placeholder.py` automatically strips incompatible wrappers before
compiling with standalone class. If a new wrapper type appears, see
`references/miktex-tikz-debugging.md`.

### P5: Nested braces in captions
`tikz_placeholder.py` uses balanced-brace matching for `\caption{...}`
and `\captionsetup{...}`, correctly handling nested `\subref{...}` etc.

### P6: MiKTeX auto-install on first run
First-time compilation downloads missing packages. This can take 2-5 minutes.

### P7: KFX conversion limit (~190 MathML blocks)
Kindle Previewer 3 has an internal limit. If KFX fails but EPUB succeeds,
push EPUB instead: `mcp_tokindle_send_to_kindle(file_id, format="epub")`.
Or split the paper into two halves at a natural section boundary.

### P8: Multi-file project structure
Some papers use `\include` instead of `\input`. tex2md.py handles both.
Main file detection: looks for `\documentclass`, then tries `main.tex`,
`0.main.tex`, `paper.tex`.

### P9: Complex custom macros
Macros with optional arguments may not expand correctly. Check output for
unexpanded commands — the LLM can fix simple cases in Step 4.

### P12: Tex2md may leave stray \parencite with lost closing braces
Some papers define `\newcommand{\citep}[1]{\parencite{#1}}`. After macro
expansion, `\parencite{...}` appears in text. tex2md v3.1 now handles this.
For older versions, convert `\parencite{key}` → `[key]` in Step 4.

### P13: Leaked formulas from align* environments
Multi-line derivations in `\begin{align*}...\end{align*}` sometimes lose
their `$$` wrappers. tex2md v3.1 now has `_wrap_leaked_math_blocks()` in
`_cleanup` to detect and re-wrap them. Legacy fix: check for lines of
pure LaTeX math without `$$` wrappers and wrap them.

### P10: DO NOT use read_file + write_file to modify files (v3.5 update)
The `read_file` tool returns content with embedded line numbers
(e.g., `60|def _strip_twoarg...`). If you pass that content to `write_file`,
it writes the line-numbered version back, CORRUPTING THE FILE.

**CRITICAL — this applies to `execute_code` too:** `execute_code`'s
`read_file()` (from `hermes_tools`) also returns line-numbered content.
If you call `read_file()` in execute_code, then pass the result to
`write_file()` (hermes_tools) or Python's `open().write()`, you corrupt
the file. This happened during Kimi Linear conversion — the entire
pipeline had to be re-run (tex2md + 3 renderers) because write_file
wrote line-prefixed content back to paper.md.

For reading an MD file to analyze it in Step 4, `read_file` is fine (you're
just looking at the content). But if you need to read raw content for
programmatic modification, use **only `terminal` with a standalone Python
script** — write the script with `write_file`, run it with `terminal`, and
use Python's built-in `open()` to read and write the MD file directly.
Do NOT use `read_file` → `write_file` (either directly or through
execute_code). Do NOT use execute_code's `write_file` on any MD file.

### P11: patch can split function/method signatures
When using `patch` to replace a method definition, if the `old_string`/
`new_string` boundary falls inside the signature line, the method can end
up with a broken signature (parameters on a separate line from `def`).
Always run `py_compile` after patching Python files to catch syntax errors.

### P14: Complex tables → image rendering (v3.2)
Tables with `@{}`, `>{}`, or `!{}` column specs are now emitted as
`<!-- TABLE_RAW -->` blocks and rendered as PNG images by `table_renderer.py`.
This is run in Step 3b, before the LLM post-processing step.

### P15: Regex `\|` matches everything (empty-string alternation bug)

See `references/regex-pitfalls.md` for full details and verification code.

### P16: `re.escape` with non-raw Python strings corrupts backslash sequences
When calling `re.escape(cmd)` where `cmd` is a non-raw string like
`'\\raisebox'`, Python interprets `\r` as a carriage return (ASCII 13)
BEFORE `re.escape` sees it. The result is a regex that matches `\r` (CR)
instead of `\r` (backslash-r).

**Fix:** Always pass raw strings to `re.escape`: use `r'\raisebox'` not
`'\\raisebox'`. In `_cleanup`, all `_strip_twoarg_command` calls now use
`r'\textcolor'`, `r'\colorbox'`, `r'\raisebox'`.

### P17: `\raisebox` inside `\footnote{}` survives because of processing order
`_process_references` handles `\footnote{content}` → `(content)` BEFORE
`_cleanup` runs its raisebox stripper. So `\raisebox` inside footnotes
gets "locked in" and leaves orphan `{0pt{...}}` patterns.

**Fix:** `_cleanup` now has `_clean_orphan_dimen_braces()` and
`[scale=...]{path}` cleanup as a final pass. The `_strip_twoarg_command`
calls also use `re.escape` with raw strings (P16) to correctly match
the command. Remaining orphan patterns like `{0pt{` in the abstract
should be caught by the quality scan in Step 5.

### P23: `&` alignment markers render as literal & on Kindle (v3.3)

After tex2md unwraps `aligned`/`align` environments, their column alignment
markers (`&`, `&&`, `&=&`) survive in the `$$` blocks. MathML/latex2mathml
renders these as literal `&` characters on Kindle — not as spacing.

**Fix (in md2kfx.py `clean_latex_source`, before latex2mathml conversion):**
```python
latex = latex.replace('&=&', '=')
latex = latex.replace('&&', '')
latex = latex.replace('&', ' \\qquad ')
```
`\qquad` produces proper MathML spacing. Plain space ` ` does NOT reliably
render in MathML.

DO NOT put this in tex2md.py — it belongs in the math→MathML pipeline
where it runs on every paper without extra steps.

### P18: Odd $$ count — cascade debugging (v3.2)

When `$$` count is odd after tex2md conversion, there's at least one
unmatched display-math delimiter. Because `$$` matching is stack-based
(open on first `$$`, close on next), a single error cascades forward,
corrupting pairing for every subsequent `$$` block — often manifesting
200+ lines away from the root cause.

**Detection (stack-based matching):**
```python
with open("paper.md", "r", encoding="utf-8") as f:
    lines = f.readlines()
stack = []
for i, line in enumerate(lines, 1):
    pos = 0
    while True:
        idx = line.find('$$', pos)
        if idx == -1: break
        if not stack: stack.append((i, idx))
        else: stack.pop()
        pos = idx + 2
print(f"Unmatched: {len(stack)}")
for s in stack:
    print(f"  L{s[0]} (col {s[1]})")
```

**Root cause 1: `\USD($)$` from `_process_special_chars`**
`_process_special_chars` converts `\$` (escaped dollar) → `USD($)`. When a
display-math closing `$$` appears on the same line as other text (e.g.,
`\in [0,1]$$`), tex2md may split it into `\$` + `$` → `USD($)$`. The orphan
`$` initiates the cascade. **Fix:** replace `\USD($)$` → `$$`.

**Root cause 2: `$$` in Markdown table cells** (v3.5 updated)
`$\phi$` or `$\downarrow$` in simple table cells may be mangled to `$$` by
`_clean_text_content` during `_convert_tabular`. Each orphan initiates a
separate cascade. Three common patterns encountered:

1. **Synthetic task tables** (palindrome/MQAR): `| $$ | $$ | $$ |` — these
   are output-position markers where `$\downarrow$` was mangled to `$$`.
   Replace `$$` with `↓` (Unicode) since these are visual markers, not math.
   Typical: 8-13 `$$` per row on a single line.

2. **PPL metric tables**: `| Training PPL ($$) | Validation PPL ($$) |`
   where `($\downarrow$)` became `($$)`. Replace `($$)` with `($\downarrow$)`.
   The `$\downarrow$` has 2 separate inline `$` — it does NOT create a `$$`
   pair, so it's safe.

3. **Simple data tables with {rcccc...} spec**: The column spec string
   leaks into the table header (`| {rcccc} **Input** |`). Non-critical
   but clutters output.

**Fix:** Use a standalone Python script via `terminal` (NOT `execute_code`
write_file — see P10). Replace `$$` in each table row with the appropriate
substitution. Then re-verify $$ count — 67 → 44 is a typical reduction
for papers with many synthetic task examples.

**Root cause 3: Orphan from aligned unwrap**
v3.2 unwraps `aligned`/`cases`/`split`/`gathered` (their content is placed
directly inside the parent `$$` block). This may expose pre-existing `$$`
inside the aligned content. Check the TeX source for `$$` or `\begin{aligned}`
usage at the orphaned line.

**Root cause 4: Simple table header column specs leak**
When `tabular` with spec `{rcccc...}` has `$\phi$` cells, the spec string
may leak into the Markdown table header (e.g., `| {rcccc...} **Input** |`).
This is non-critical for KFX but clutters the output.

**Debugging workflow:**
1. Find the **first** orphan (earliest line number in stack output)
2. Search backward from that line for `USD($)` or `$$` in table cells
3. Fix only the root cause — the forward cascade resolves automatically
4. Re-verify with the stack diagnostic; all orphans should be gone

**Note on `check_math_delimiters.py` false alarms (v3.5):** The checker
reports excessive-length `$$` blocks (500+ chars) as `MISPAIRED_DD` with
HIGH severity. These are NOT real pairing errors — math-heavy ML papers
routinely have long display formulas. The **only actionable signals** are:
`ODD_DD_COUNT` (odd $$ count — use the stack diagnostic above to locate
the root cause), `STRAY_DD` (lone $$ mid-line), and `ODD_D_COUNT` (odd
inline $). If `issue_count > 0` but `critical_count == 0` and $$ stack
matching confirms all pairs are correct, the conversion is ready for KFX.

### P19: Stray triple backtick in prose → KFX image loss (v3.2)

The md2kfx.py `code_to_image` regex `r'```(.*?)\n(.*?)\n```'` with `re.DOTALL`
matches greedily across the entire file. If prose contains ``` (e.g., as
quotation marks like `` ```<PUSH>` ``), the regex matches from that stray
fence all the way to the real code block's closing ```, consuming ALL content
in between — including image references, formulas, and sections.

**Symptoms:** KFX has fewer images than expected; the EPUB `images/` dir is
missing several JPEGs/PNGs. `code_to_image` generates unexpected code-PNGs.

**Fix:** Before KFX conversion, scan for stray ``` in prose and replace with
single backtick `` ` `` (or use ```` ``` ````  if intended as literal backticks).

### P20: `\bm x` single-char form (v3.2)

tex2md.py converts `\bm{...}` → `\boldsymbol{...}` but `\bm x` (single char,
no braces) was not handled. **Fix (in tex2md.py `_process_math`):**
```python
content = re.sub(r'\\bm\s+([a-zA-Z])', r'\\boldsymbol{\1}', content)
```
For LLM post-processing: search for `\bm ` (with space) and wrap the
following single character in braces.

### P21: Broken `$...$$...$` math nesting (v3.2)

When `aligned` is unwrapped inside an inline-math context (`$\mathbf{S}_t =
\left(\n$$\n...\n$$\n$`), the nested display `$$` inside inline `$` creates
invalid markup. **Fix:** remove the outer `$...$` wrapper and keep only the
`$$...$$` block. This pattern appears in sections where the original LaTeX had
`$\begin{aligned}...\end{aligned}$` — tex2md converts `aligned` first
(unwrapping it), then the outer `equation` wraps content in `$$`, creating
the nesting conflict.

### P22: Code listings in figure+subfigure+minted lost (v3.3)

`figure` environments containing `subfigure` + `minted` code blocks are not
converted by tex2md. Both the code content and the side-by-side layout are lost.
Only a simple text reference (`Listing~(listing:xxx)`) survives.

**Workflow:** Render the original .tex listing file as a standalone image,
similar to TikZ figures:
```bash
# 1. Wrap the listing .tex in standalone doc with minted support
# 2. Compile: pdflatex -shell-escape listing.tex
# 3. Convert PDF → PNG via pymupdf
# 4. Inject ![caption](images/listing_xxx.png) at the Listing reference
```
Required preamble packages: `minted`, `subcaption`, `fancyvrb`, `tcolorbox`,
`geometry`. Add custom colors from main.tex.

### P24: `\r\n` Windows line endings break renderer regex (v3.3.1)

`table_renderer.py` and `code_renderer.py` use `\n` in their block-matching
regex patterns:

```python
r'<!-- TABLE_RAW:(\d+)\|(.+?) -->\n(.*?)\n<!-- /TABLE_RAW:\1 -->'
r'<!-- CODE_RAW:(\d+)\|(.*?) -->\n(.*?)\n<!-- /CODE_RAW:\1 -->'
```

On Windows, tex2md produces `\r\n` line endings. The `\n` does not match
`\r\n`, so the renderers find 0 blocks — silently skipping all TABLE_RAW
and CODE_RAW markers.

**Fix (applied):** Replace `\n` with `[\r\n]+` in both scripts:

```python
r'<!-- TABLE_RAW:(\d+)\|(.+?) -->[\r\n]+(.*?)[\r\n]+<!-- /TABLE_RAW:\1 -->'
r'<!-- CODE_RAW:(\d+)\|(.*?) -->[\r\n]+(.*?)[\r\n]+<!-- /CODE_RAW:\1 -->'
```

**Symptom:** Renderer reports "Found N block(s)" where N < expected count,
or "Found 0 block(s)" when the MD file clearly contains markers.

### P26: `patch` tool corrupts `\r` in LaTeX content on Windows (v3.5)

The `patch` tool interprets `\r` as a carriage return (ASCII 13, matching
`\r\n` Windows line endings). When LaTeX content contains `\r` — as in
`\right)`, `\raisebox`, `\renewcommand`, `\rm`, `\ref`, etc. — the naive
find-and-replace splits the text at the `\r` boundary, producing mangled
output like `\r\night)` instead of `\right)`.

**This happened during Kimi Linear conversion** when trying to fix the P21
`$...$$...$$...$` pattern via `patch`. The fix contained `\right)` which
got split into `\r` + `ight)`.

**Safe alternatives (in order of preference):**

1. **Write a standalone Python script, run via `terminal`** — uses
   Python's `open().read()` + `str.replace()` + `open().write()`, which
   handles `\r\n` correctly. This is the most reliable approach.

2. **Use `execute_code` with Python's `open()` (NOT write_file)** — read
   with `open()`, modify, write back with `open()`. But DO NOT use
   `execute_code`'s `write_file()` or `read_file()` from hermes_tools
   (see P10).

3. **Use `patch` with `replace_all=true` only** if the content is simple
   prose with no backslash commands. Avoid `patch` for any LaTeX content
   containing `\r`-prefixed commands.

**Detection:** After any modification, verify `\right)`, `\raisebox` etc.
have not been corrupted. Count `ight)` occurrences — each is a broken
`\right)` that needs repair.

### P27: Kindle shows image placeholders — MCP server path mismatch (v3.7)

When using `mcp_tokindle_upload_local_file`, the MCP server copies images to
`UPLOAD_FOLDER/{file_id}_images/`, but `MarkdownToKFX` looks for images at
`UPLOAD_FOLDER/images/` (resolved from `self.md_file.parent / 'images'`).

**Symptoms:** KFX file is much smaller than expected (~760KB vs ~2.5MB for a
typical paper with 13 images). Kindle shows placeholder icons where images
should be. The EPUB also lacks images (check `EPUB/images/` in the zip).

**Root cause:** `mcp_server.py` line 284 uses `f"{file_id}_images"` as the
destination directory, but `MarkdownToKFX.markdown_to_html()` at line 783 does:
```python
src_path = self.md_file.parent / 'images' / img_name
```
The `_images` suffix creates a path mismatch. Images are silently skipped
(a `[Warning]` is printed but the conversion continues without images).

**Fix (applied to `mcp_server.py`):**
```python
# BEFORE (broken):
dest_images_dir = UPLOAD_FOLDER / f"{file_id}_images"

# AFTER (fixed):
dest_images_dir = UPLOAD_FOLDER / 'images'
dest_images_dir.mkdir(exist_ok=True)
for img_file in src_images_dir.iterdir():
    if img_file.is_file():
        shutil.copy2(img_file, dest_images_dir / img_file.name)
```

**Verification:** After conversion, check `OUTPUT_FOLDER/<file_id>.kfx` size —
it should be >2MB for a math-heavy paper with images. See
`references/md2kfx_image_handling.md` for full diagnostic workflow.

### P25: Removed (v3.6)

Image format choice (PNG vs JPEG) is not the root cause of Kindle display issues.
The renderers may use either format. The md2kfx.py pipeline handles format
conversion as needed for the target format (EPUB/KFX).

### TikZ Placeholder Format

tex2md.py emits `<!-- TIKZ_FIGURE:figures/mainfig.tex -->` for detected
TikZ/pgfplots figures. tikz_placeholder.py resolves them with MiKTeX.

### Missing Image Handling

When `\includegraphics{file.pdf}` can't be resolved, a second attempt is
made in Step 3, searching tex_dir and figures/ subdirectory.
