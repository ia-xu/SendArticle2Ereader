---
name: fix_tokindle
description: >
  Debug and fix tokindle md2kfx.py conversion failures (KFX internal error,
  garbage MathML, broken formulas). Documents the md2kfx pipeline, known
  failure points, diagnostic methods, and requires subagent-based binary
  search to minimize token usage.
version: 1.0.0
author: Hermes Agent
platforms: [windows]
metadata:
  hermes:
    tags: [tokindle, md2kfx, kfx, debug, mathml, kindle]
---

# Fix tokindle md2kfx Conversion Failures

Use when KFX conversion fails with "Kindle conversion has encountered an
internal error", or when generated MathML is malformed/garbage.

## md2kfx Pipeline Overview

Source: `D:/data/anan/projects/tokindle/src/md2kfx.py`
Python env: `D:/storage/program/miniconda/envs/anxu/python.exe`

```
convert()
 ├── markdown_to_html()           ← Step 1: MD → HTML
 │    ├── process_math_formulas()  ← 1a: formula conversion (MOST BUG-PRONE)
 │    │    └── preprocess_md()     ← 1a-1: regex cleanup (SECOND MOST BUG-PRONE)
 │    ├── extract_toc()            ← 1b: heading → TOC structure
 │    ├── add_anchor_ids()         ← 1c: inject {#anchor} IDs
 │    ├── generate_toc_html()      ← 1d: build TOC <ul> tree
 │    ├── image processing         ← 1e: download/copy/convert images
 │    └── md.convert()             ← 1f: Python-Markdown library → HTML
 │
 ├── create_epub()                 ← Step 2: HTML → EPUB (ebooklib)
 │    └── pack images, TOC, spine
 │
 └── epub_to_kfx()                 ← Step 3: EPUB → KFX (Calibre + Kindle Previewer 3)
      └── ebook-convert.exe → Kindle Previewer 3 CLI
```

## Known Failure Points

### FP1: preprocess_md regex destroys legitimate $$ (FIXED 2026-07-12)

**Location**: `preprocess_md()`, ~line 380

**Bug**: The regex `(?<!\$)\$\$(?!\$)(?!\s*$)(?!\s*\n)` was intended to fix
stray `$$` from Zhihu/WeChat copy-paste artifacts. But it matched ANY `$$`
followed by non-whitespace — including legitimate block formula openers like
`$$\mathbb{E}...`. It replaced the opening `$$` with `$`, leaving the closing
`$$` orphaned.

**Cascade effect**:
1. `$$\mathbb{E}\left[...\right]$$` → `$\mathbb{E}\left[...\right]$$`
2. Block regex `\$\$(.*?)\$\$` no longer matches (opening `$$` is gone)
3. The orphaned closing `$$` plus nearby inline `$` signs get matched by
   the inline regex `\$([^\$]+)\$` across paragraph boundaries
4. Ordinary English text gets sent to `latex2mathml.converter.convert()`
5. Each letter becomes `<mi>x</mi>` — garbage MathML
6. Kindle Previewer 3 crashes: "internal error"

**Fix applied**: Commented out the regex. Block formulas are handled by
`\$\$(.*?)\$\$` (DOTALL) which is correct. Stray `$$` in text is cosmetic
(displays as literal `$$`) and non-fatal.

**How to detect regression**: Check `preprocess_md` output for $$ count
before vs after. If $$ count drops by ~50%, this regex is active again.

### FP2: inline $ regex crosses block-level MathML HTML (FIXED 2026-07-12)

**Location**: `process_math_formulas()`, ~line 575-585

**Bug**: After converting `$$...$$` blocks to `<div class="math-block">...MathML...</div>`,
the code immediately runs `\$([^\$]+)\$` on the ENTIRE content. This regex
matches across the already-inserted HTML, picking up stray `$` characters
from later inline formulas and wrapping all the text + HTML in between as
a single inline MathML element.

**Fix applied**: Block-level MathML output is stashed into placeholders
(`BLOCKMATHSTASH{n}ENDSTASH`) before inline conversion, then restored after.

**How to detect**: Extract EPUB, inspect `content.xhtml`. If `<span class="math-inline">`
contains sequences like `<mi>i</mi><mi>s</mi><mi>t</mi><mi>h</mi><mi>e</mi>`
(spelling out English words letter-by-letter), this bug is present.

### FP3: preprocess_md dedup regex catastrophic backtracking

**Location**: `preprocess_md()`, line 282

**Regex**: `\$\$(.*?)\$\$\s*\1` with `re.DOTALL`

**Risk**: The backreference `\1` means "the same content as group 1". If
the content between `$$...$$` contains regex metacharacters or is very long,
this can cause exponential backtracking. Observed as conversion timeout
(html generation taking >60s on a 40KB file).

**Mitigation**: Not yet a confirmed failure. If conversion hangs at
`process_math_formulas`, this regex is the prime suspect. Test by commenting
it out and re-running.

### FP4: clean_latex_source over-strips [number] patterns

**Location**: `clean_latex_source()`, ~line 533

**Regex**: `\[\d+(?:\.\d+)?(?:pt|em|ex|cm|mm)?\]`

**Risk**: This removes `[10pt]`, `[5em]` etc. from LaTeX formulas. But if
a formula contains legitimate `[1]` (e.g. `\sum_{i \in [1,N]}`), the `[1]`
gets stripped, corrupting the formula. Usually cosmetic (wrong rendering)
but could cause latex2mathml to fail.

### FP5: Multi-chapter EPUB fails Kindle Previewer

**Location**: `epub_to_kfx()` → Kindle Previewer 3

**Bug**: Kindle Previewer 3 throws "internal error" when a single
`content.xhtml` contains content from multiple book chapters merged together.
Not a file-size issue — even moderate-size multi-chapter files fail while
single-chapter files of the same size succeed.

**Workarounds**:
- Convert each chapter individually
- Push EPUB format instead of KFX (`send_to_kindle(format="epub")`)

### FP6b: Stray $$ / unpaired $ from malformed source (FIXED 2026-07-23)

**Location**: Source Markdown file (not md2kfx.py)

**Bug**: arXiv→Markdown conversion (tex2md.py) can produce stray `$$` markers
and odd-count `$` signs. When `$$...$$` regex pairs are misaligned (odd number
of `$$`, or a stray `$$` mid-line), one block-formula match captures headings
and English prose between two distant `$$` markers. All this text gets sent
to `latex2mathml.converter.convert()`, producing massive garbage MathML
(43K+ `<mi>` tags spelling English words letter-by-letter), which crashes
Kindle Previewer 3.

**Detection**: Run `check_math_delimiters.py` BEFORE KFX conversion:
```bash
"D:/storage/program/miniconda/envs/anxu/python.exe" \
  "D:/data/anan/projects/tokindle/scripts/check_math_delimiters.py" <md_file>
```
The script reports: ODD_DD_COUNT, ODD_D_COUNT, STRAY_DD, MISPAIRED_DD,
EMPTY_DD_PAIR — with line numbers, context, and fix suggestions.

**Fix**: Fix the SOURCE Markdown file, not md2kfx.py:
1. Run the checker
2. Read the JSON report + affected MD lines
3. Fix stray `$$` → `$` (inline formula end typo)
4. Remove orphan standalone `$$` lines (lost partners from split equations)
5. Re-run checker until `issue_count == 0`
6. Then convert to KFX

**Why not fix in md2kfx.py**: Adding validation logic inside md2kfx only
hides the symptom (filters garbage MathML) but loses formula rendering.
The correct approach is to fix `$` pairing in the source MD so all formulas
render correctly.

**Full case study**: See `references/math-delimiter-debugging.md` for the
Kimi Linear paper debugging session — 5 fix patterns, fix ordering, and
verification methodology.

### FP6: MCP conversion thread dies on child process kill

**Location**: tokindle MCP server daemon thread

**Bug**: If `ebook-convert.exe` or `calibre-parallel.exe` is killed while
the MCP background thread is running KFX conversion, the thread becomes
permanently unresponsive. All subsequent `upload_local_file` calls show
`status: "uploaded"` forever.

**Fix**: Restart Hermes (which restarts the MCP server). Or bypass MCP
entirely — call `MarkdownToKFX.convert()` directly via Python script.

## Diagnostic Methods

### D1: Extract EPUB and inspect XHTML

When KFX conversion fails, the EPUB is still generated. Extract and inspect:

```python
import zipfile
from pathlib import Path

epub_path = Path("path/to/book.epub")
with zipfile.ZipFile(epub_path) as z:
    content = z.read("EPUB/content.xhtml").decode("utf-8")

# Check for garbage MathML (letters spelled out as <mi>x</mi>)
import re
spans = re.findall(r'<span class="math-inline">(.+?)</span>', content, re.DOTALL)
for i, span in enumerate(spans):
    if re.search(r'<mi>[a-z]</mi><mi>[a-z]</mi>', span):
        word = "".join(re.findall(r"<mi>([a-z])</mi>", span))
        print(f"BROKEN span {i}: {word[:50]}")

# Check XML well-formedness
from xml.etree import ElementTree as ET
try:
    ET.fromstring(content)
    print("XML: well-formed")
except ET.ParseError as e:
    print(f"XML: MALFORMED - {e}")

# Count remaining $ (should be 0 after conversion)
print(f"Remaining $: {content.count('$')}")
```

### D2: Trace process_math_formulas step by step

```python
import sys, re
sys.path.insert(0, "D:/data/anan/projects/tokindle")
from src.md2kfx import MarkdownToKFX
from pathlib import Path

md_path = Path("path/to/input.md")
converter = MarkdownToKFX(str(md_path), "test.kfx", title="test", author="test")
content = md_path.read_text(encoding="utf-8")

# Step 1: preprocess_md
pre = converter.preprocess_md(content)
print(f"preprocess_md: {len(content)} → {len(pre)} chars")
print(f"$$ before: {content.count('$$')}, after: {pre.count('$$')}")
# If $$ count dropped significantly, FP1 is active

# Step 2: process_math_formulas (may be slow if FP3 is triggered)
import time
t0 = time.time()
result = converter.process_math_formulas(pre)
print(f"process_math_formulas: {time.time()-t0:.1f}s, {len(pre)} → {len(result)} chars")
print(f"Remaining $: {result.count('$')}")
```

### D3: Run ebook-convert with verbose logs

```python
import subprocess

cmd = [
    r"C:\Program Files\Calibre2\ebook-convert.exe",
    epub_path, kfx_path,
    "--authors", "test", "--title", "test",
    "--show-kpr-logs"
]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                       creationflags=0x08000000)  # CREATE_NO_WINDOW
# Look for "Conversion Failure Reason" and "Summary_Log.csv" in stdout
```

## Efficient Debugging Strategy (MANDATORY)

When KFX conversion fails, do NOT read the full 930-line md2kfx.py into
context or manually trace every line. Instead:

### Step 1: Quick diagnosis via EPUB inspection (use subagent)

Delegate EPUB extraction + XHTML analysis to a subagent to keep your context clean:

```
delegate_task(
  goal="Diagnose KFX conversion failure by inspecting the generated EPUB",
  context="""
    EPUB path: <path>
    Python: D:/storage/program/miniconda/envs/anxu/python.exe
    
    Extract EPUB/content.xhtml from the EPUB. Check:
    1. XML well-formedness
    2. Count <math> elements, count remaining $ signs
    3. Find garbage MathML: spans where <mi> tags spell out English words
    4. Report the first 3 broken spans with surrounding context
  """,
  toolsets=["terminal"]
)
```

### Step 2: Binary search the failing content (use subagent)

If the EPUB has garbage MathML, the input Markdown has a `$` pairing issue.
Binary-search to find the exact paragraph:

```
delegate_task(
  goal="Binary search which paragraph of a Markdown file causes garbage MathML",
  context="""
    MD file: <path>
    Images dir: <path>/images/
    Python: D:/storage/program/miniconda/envs/anxu/python.exe
    md2kfx.py: D:/data/anan/projects/tokindle/src/md2kfx.py
    
    Split MD at paragraph boundaries. For each test subset:
    1. Write test_N_M.md with paragraphs N to M
    2. Copy images dir alongside
    3. Run: MarkdownToKFX(md_path, kfx_path, title='test', author='test').convert()
    4. Check if result ends with .kfx (success) or .epub (failure)
    5. Each conversion takes ~60-90s. Run SEQUENTIALLY.
    
    Report the exact paragraph index that triggers the failure.
  """,
  toolsets=["terminal"]
)
```

### Step 3: Apply fix

**For `$`/`$$` delimiter issues (FP6b — MOST COMMON for arXiv papers):**
Fix the SOURCE Markdown file, NOT md2kfx.py. Run `check_math_delimiters.py`,
read the JSON report, fix stray `$$`/orphan `$` in the MD, re-run checker
until `issue_count == 0`. See `references/math-delimiter-debugging.md` for
the full case study with 5 fix patterns.

**For md2kfx.py internal bugs (FP1–FP4):**
Apply a targeted patch to `D:/data/anan/projects/tokindle/src/md2kfx.py`
using the `patch` tool. Do NOT rewrite the entire file.

**CRITICAL**: Do NOT add validation/filtering logic inside md2kfx.py to
"catch" garbage MathML. This hides the symptom but loses formula rendering.
Always fix the root cause in the source MD or the conversion regex.

### Step 4: Verify full pipeline (MANDATORY)

After ANY fix, re-run the COMPLETE conversion end-to-end and confirm the
result is `.kfx`, not `.epub`. A fix is not done until the KFX file exists:

```python
import sys
sys.path.insert(0, "D:/data/anan/projects/tokindle")
from src.md2kfx import MarkdownToKFX

converter = MarkdownToKFX(md_path, kfx_path, title="...", author="...")
result = converter.convert()
# Success: result is a .kfx Path
# Failure: result is a .epub Path (KFX conversion fell back)
```

Or via MCP: `mcp_tokindle_get_file_info(file_id)` — check `has_kfx: true`
and `status: "converted"` (not `"converted_epub"`).

## Common Fix Patterns

### Pattern A: Disable dangerous regex in preprocess_md

Many bugs come from preprocess_md regexes that were designed for Zhihu/WeChat
edge cases but break on general LaTeX content. When a regex in preprocess_md
is identified as the cause:

```python
# Comment it out with explanation:
# content = re.sub(r'dangerous_pattern', 'replacement', content)
```

Then verify that the downstream `\$\$(.*?)\$\$` and `\$([^\$]+)\$` regexes
in `process_math_formulas` handle the content correctly without the
preprocessing step.

### Pattern B: Stash/restore for sequential regex operations

When two regex operations run on the same content sequentially, the first
regex's output can interfere with the second. Use placeholder stash/restore:

```python
placeholders = {}
counter = [0]
def stash(match):
    key = f"STASH{counter[0]}ENDSTASH"
    counter[0] += 1
    placeholders[key] = match.group(0)
    return key

# Stash first regex output
content = re.sub(r'<div class="math-block">.*?</div>', stash, content, flags=re.DOTALL)

# Run second regex (won't match across stashed content)
content = re.sub(r'\$([^\$]+)\$', transform, content)

# Restore
content = re.sub(r'STASH\d+ENDSTASH', lambda m: placeholders[m.group(0)], content)
```

### Pattern C: Bypass MathML with skip_mathml=True

If MathML conversion is fundamentally broken for a specific input and a
quick fix is needed:

```python
converter = MarkdownToKFX(md_path, kfx_path, title="...", author="...",
                          skip_mathml=True)
```

This converts `$...$` to `[...]` and `$$...$$` to `[...]` (plain text in
brackets). Formulas won't render as math but KFX conversion will succeed.

### Pattern D: Fix $ delimiter pairing in source MD (PREFERRED for arXiv papers)

When garbage MathML comes from stray `$$` or unpaired `$` in the source
Markdown (not from md2kfx.py bugs), fix the SOURCE file:

1. Run `check_math_delimiters.py` on the MD file
2. Read the JSON report — fix types: STRAY_DD, MISPAIRED_DD, ODD_D_COUNT
3. Apply targeted patches to the MD file (not md2kfx.py!)
4. Re-run checker until `issue_count == 0`
5. Re-convert to KFX and verify

See `references/math-delimiter-debugging.md` for 5 real-world fix patterns
from the Kimi Linear paper case study.

This is the PREFERRED fix because it preserves formula rendering. Adding
validation inside md2kfx.py (Pattern A/B) only hides the symptom — the
formulas that should have been in those `$$` pairs are silently dropped.

## File Locations

- md2kfx.py: `D:/data/anan/projects/tokindle/src/md2kfx.py`
- MCP server: `D:/data/anan/projects/tokindle/mcp_server.py`
- Python env: `D:/storage/program/miniconda/envs/anxu/python.exe`
- Calibre ebook-convert: `C:\Program Files\Calibre2\ebook-convert.exe`
- Kindle Previewer 3 logs: `%TEMP%/calibre-*/[hash]/[hash]/0000/` (look for `log_KPR_CLI.txt`, `Summary_Log.csv`)
