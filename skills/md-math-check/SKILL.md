---
name: md-math-check
description: >-
  Fix $ / $$ delimiter pairing issues in any Markdown file before KFX
  conversion. Runs check_math_delimiters.py to find problems (stray $$,
  orphan $, odd count), then LLM reads the report + MD to apply targeted
  fixes. Also handles disambiguating currency $ vs math $ — currency $
  is rewritten to USD($) to bypass math processing. Works for any MD
  source: arXiv, Zhihu, WeChat, manual uploads.
  TRIGGER: KFX conversion fails with "converted_epub" (no KFX) on a file
  containing math formulas, OR proactively before converting any
  math-heavy article ($...$ or $$...$$ present in the MD).
version: 1.1.0
author: Hermes Agent
platforms: [windows]
metadata:
  hermes:
    tags: [tokindle, mathml, kfx, markdown, debug, formula]
---

# Fix Markdown $ Delimiter Issues Before KFX Conversion

## When to Use

**Reactive (KFX failed):** KFX conversion returns `status: "converted_epub"`
(EPUB generated but KFX failed). The MD file contains `$` or `$$` markers.
This usually means `$` / `$$` delimiters are mis-paired, producing garbage
MathML that crashes Kindle Previewer 3.

**Proactive (before conversion):** You're about to convert a math-heavy MD
file (arXiv paper, technical article). Run the checker first to catch pairing
issues before they cause a failed KFX conversion.

## Root Cause

md2kfx.py converts `$...$` → inline MathML and `$$...$$` → block MathML using
sequential regex matching. If `$` / `$$` markers are mis-paired (stray `$$`,
orphan `$`, odd count), the regex wraps English prose as fake formulas, producing
garbage MathML (40K+ `<mi>` tags spelling English words). Kindle Previewer 3
crashes with "internal error".

**Common causes by source:**

| Source | Typical Problem |
|--------|----------------|
| arXiv TeX → MD (tex2md.py) | Stray `$$` from split equations, orphan `$$` lines |
| arXiv HTML → MD | `$` inside citation brackets, broken inline math |
| Zhihu | `$$` copy-paste artifacts, incomplete formula rendering |
| WeChat | `$` used as dollar sign (price), not math delimiter |
| Manual upload | Any of the above |

## Prerequisites

- Check script: `D:/data/anan/projects/tokindle/scripts/check_math_delimiters.py`
- Python: `D:/storage/program/miniconda/envs/anxu/python.exe`

## Workflow

### Step 1: Run the Checker

```bash
PYTHON="D:/storage/program/miniconda/envs/anxu/python.exe"
CHECKER="D:/data/anan/projects/tokindle/scripts/check_math_delimiters.py"

"$PYTHON" "$CHECKER" "<md_file_path>"
```

Output is JSON with:
- `dd_paired` / `d_paired`: whether `$$` and `$` counts are even
- `issues[]`: detailed list with line numbers, context, severity, suggestions

**If `issue_count == 0`:** No problems. The KFX failure is caused by something
else (see fix_tokindle skill for other failure modes).

**If `issue_count > 0`:** Continue to Step 2.

### Step 2: Read Report + Fix MD

Read the JSON report, then read the affected lines of the MD file. Apply fixes
based on issue type:

#### Issue: STRAY_DD (stray `$$` mid-line)

A `$$` appears with text both before AND after on the same line. This is the
most common and most destructive issue — it shifts ALL subsequent `$$` pairing.

**Fix:** Determine whether the `$$` should be `$` (inline formula end):

```
Line 50: $\mathcal{A}_{[t]} :=...^{C\times C}$$ is the matrix
                                    ^^
```

Here the `$$` ends an inline formula → change to `$`:

```
$\mathcal{A}_{[t]} :=...^{C\times C}$ is the matrix
```

Use `patch` tool: `old_string` = the full line with `$$`, `new_string` = same
line with `$`.

#### Issue: ODD_DD_COUNT (odd number of `$$`)

One or more `$$` has no partner. Usually caused by a STRAY_DD (fix that first),
or an orphan `$$` on its own line (from a split equation that lost its partner
during conversion).

**Fix:**
1. Check STRAY_DD issues first — fix those, re-run checker
2. If still odd: look for standalone `$$` lines (the checker reports these)
3. If the standalone `$$` is a formula fragment with no matching opener/closer
   nearby → delete it. The formula was already broken during conversion.
4. If it's a formula closer with a nearby formula fragment → wrap the fragment
   in `$$...$$`

#### Issue: MISPAIRED_DD (pair content contains prose)

This is a **symptom** of a stray `$$` elsewhere — NOT a standalone bug. The fix
is always to fix the root-cause STRAY_DD or ODD_DD_COUNT first, then this
resolves automatically. Re-run the checker after fixing stray `$$`.

#### Issue: ODD_D_COUNT (odd number of single `$`)

A single `$` is unpaired. Three possible causes:

**Case A — Orphan `$` from table/formula fragment:**

```
Line 557: ' $ &'          ← formula fragment lost during conversion
```

Fix: delete the orphan `$`.

**Case B — `$` used as dollar sign (currency):**

```
Line 42: The price is $50 per month.
```

Fix: replace with `USD($)` — md2kfx.py converts this to `&#36;` (literal dollar
sign), bypassing math processing:

```
The price is USD($)50 per month.
```

**Case C — Missing `$` partner (formula not properly closed):**

```
Line 120: The value of $\alpha$ is set to $5.
                                        ^ unpaired
```

Fix: if `$5` is a formula → add closing `$` (`$5$`). If `$5` is a price → `USD($)5`.

**How to distinguish currency from math:**
- Currency: `$` followed by a plain number, in a price/cost context
- Math: `$` followed by LaTeX commands (`\alpha`, `\mathbf`, `\frac`), variables,
  or mathematical expressions
- Ambiguous: read surrounding sentences to determine context

#### Issue: EMPTY_DD_PAIR ($$ immediately followed by $$)

$$ with no content between. Delete both markers.

### Step 3: Re-run Checker

```bash
"$PYTHON" "$CHECKER" "<md_file_path>"
```

**Must reach `issue_count == 0`** before converting. If issues remain:
- Fix them, re-run, repeat
- If stuck on a complex case, use `read_file` to read surrounding context

### Step 4: Convert to KFX

Now the MD file has properly paired `$` / `$$`. Convert via MCP or direct:

```bash
mcp_tokindle_upload_local_file(file_path="<md_file>", title="...", author="...")
# Wait ~2 min, poll get_file_info until status="converted" and has_kfx=true
```

## How the Checker Works

`check_math_delimiters.py` scans the MD file for:

| Check | Severity | Detection |
|-------|----------|-----------|
| ODD_DD_COUNT | CRITICAL | `$$` count is odd → unpaired block delimiter |
| ODD_D_COUNT | CRITICAL | `$` count (excluding `$$`) is odd → unpaired inline |
| STRAY_DD | HIGH | `$$` with non-whitespace text before AND after on same line |
| MISPAIRED_DD | HIGH | `$$` pair whose content contains headings/prose/code |
| EMPTY_DD_PAIR | MEDIUM | `$$` immediately followed by `$$` with no content |

## File Locations

- Check script: `D:/data/anan/projects/tokindle/scripts/check_math_delimiters.py`
- md2kfx.py: `D:/data/anan/projects/tokindle/src/md2kfx.py`
- Python env: `D:/storage/program/miniconda/envs/anxu/python.exe`

## Related Skills

- `tokindle`: Web articles → KFX (Zhihu, WeChat, arXiv)
- `tex_to_kindle`: arXiv TeX source → KFX (includes this check as Step 2.5)
- `fix_tokindle`: General KFX conversion debugging (FP6b references this skill)
