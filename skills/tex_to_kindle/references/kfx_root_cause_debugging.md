# KFX Conversion Root-Cause Debugging

Full trace of the md2kfx.py `$$` regex bug that caused KFX conversion failures
for TeX-to-Markdown papers. Documented as a methodology reference for future
KFX conversion debugging.

## Symptom

- Full paper Markdown (40KB, 6 block formulas + 79 inline formulas) → KFX fails
  with "Kindle conversion has encountered an internal error"
- EPUB succeeds (57KB)
- With `skip_mathml=True`, KFX succeeds (2.1MB) → problem is in MathML generation
- Individual sections convert fine; only the combined full document fails

## Debugging Methodology

### Step 1: Binary Search with KFX Conversion

Split the Markdown at paragraph boundaries, convert each half to KFX:

```python
import re
paras = re.split(r'\n\n+', content)
mid = len(paras) // 2
# Write each half as separate .md files with images/ dir
# Run md2kfx conversion on each
```

Run conversions **sequentially** (parallel conversions compete for resources).
Each takes ~60-90s. Check if result ends with `.kfx` (success) or `.epub` (failure).

Narrow: if first_half fails, split into quarters. Continue until the minimal
failing combination is found.

**Key finding:** Individual quarters all succeeded, but their combination failed.
This ruled out a single bad paragraph and pointed to a cumulative/interaction bug.

### Step 2: Inspect the Generated XHTML

Extract the EPUB and inspect `EPUB/content.xhtml`:

```python
import zipfile
with zipfile.ZipFile(epub_path) as z:
    content = z.read('EPUB/content.xhtml').decode('utf-8')
```

Look for MathML corruption patterns:
- `<mi>` tags spelling English words: `<mi>i</mi><mi>s</mi><mi>t</mi>` → "ist"
- `&lt;` / `&gt;` inside MathML (HTML tags leaked into math)
- Ordinary text wrapped in `<span class="math-inline">`

```python
spans = re.findall(r'<span class="math-inline">(.+?)</span>', xhtml, re.DOTALL)
for span in spans:
    if re.search(r'<mi>[a-z]</mi><mi>[a-z]</mi>', span):
        word = ''.join(re.findall(r'<mi>([a-z])</mi>', span))
        print(f"BROKEN: '{word[:30]}'")
```

### Step 3: Trace md2kfx.py Pipeline

Replicate `preprocess_md` step by step, counting `$$` marks after each regex:

```python
import re
content = open(md_path).read()

# Step 1: dedup
content = re.sub(r'\$\$(.*?)\$\$\s*\1', r'$$\1$$', content, flags=re.DOTALL)
print(f"After dedup: {content.count('$$')} $$ marks")  # Should be 12

# Step 2: THE CULPRIT
content = re.sub(r'(?<!\$)\$\$(?!\$)(?!\s*$)(?!\s*\n)', '$', content)
print(f"After culprit: {content.count('$$')} $$ marks")  # Drops to 6!
```

If `$$` count drops by half after preprocess_md, the regex is eating block-formula
openers.

### Step 4: Verify the Fix

After patching, run the full conversion and verify KFX is produced:

```python
converter = MarkdownToKFX(md_path, kfx_path, title="...", author="...")
result = converter.convert()
assert result.endswith('.kfx'), f"KFX failed: {result}"
```

## Root Cause Summary

Two bugs in md2kfx.py, both in the math processing pipeline:

### Bug 1: preprocess_md `$$` regex (L380)

```python
# BEFORE (broken):
content = re.sub(r'(?<!\$)\$\$(?!\$)(?!\s*$)(?!\s*\n)', '$', content)
```

This regex matched ANY `$$` followed by non-whitespace, including legitimate
block-formula openers like `$$\mathbb{E}`. It replaced the opening `$$` with `$`,
orphaning the closing `$$` and causing the inline regex to match across paragraphs.

**Fix:** Commented out the regex entirely. It was fundamentally flawed — cannot
distinguish stray `$$` from legitimate block-formula openers.

### Bug 2: process_math_formulas inline regex (L585)

After block-math conversion to HTML, the inline regex `\$([^\$]+)\$` ran on
the full content including the generated `<div class="math-block">...</div>` HTML.
The regex matched `$` signs across the HTML, wrapping ordinary text in MathML.

**Fix:** Stash block-level MathML HTML into placeholders before inline conversion,
restore after.

```python
# Stash block math
content = re.sub(r'<div class="math-block">.*?</div>', stash_block, content, flags=re.DOTALL)
# Run inline conversion
content = re.sub(r'\$([^\$]+)\$', inline_cleanup, content)
# Restore block math
content = re.sub(r'BLOCKMATHSTASH\d+ENDSTASH', restore_block, content)
```

## Compatibility Analysis

The disabled `$$` regex was intended for Zhihu/WeChat articles with stray `$$`
from copy-paste artifacts. Disabling it has no negative impact:

- **Block formulas** (`$$...$$`): Now work correctly (was: broken → fatal)
- **Stray `$$` in text**: Displayed as literal `$$` (was: displayed as `$` → cosmetic)
- The regex CANNOT distinguish the two cases, so it was always incorrect
- No previously-working conversion breaks from disabling it

## Files Modified

- `D:/data/anan/projects/tokindle/src/md2kfx.py` L380: commented out `$$` regex
- `D:/data/anan/projects/tokindle/src/md2kfx.py` L577: added block-math stash/restore
