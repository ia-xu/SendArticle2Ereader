# Case Study: Into Thin Air (进入空气稀薄地带) — EPUB Structure Analysis

Example of a book where the generic extract_chapters.py completely fails and custom extraction is required.

## English EPUB Structure

- 25 HTML files total
- 21 chapters, each one HTML file, named `c01_r1.htm` through `c21_r1.htm`
- 1 epilogue (`epi_r1.htm`), 1 dramatis personae (`col4_r1.htm`), 2 nav/title files
- Each chapter starts with repeated header "Into Thin Air" + word-numbered title (ONE, TWO, ... TWENTY-ONE) + location/date/altitude
- Chapter numbering: **word numbers** (ONE, TWO, THREE...) — NOT "CHAPTER 1"

## Chinese EPUB Structure

- 61 HTML files total
- **Each chapter split across TWO files**: title page (short, ~150-400 chars: chapter number + epigraph quote) + body text (~5K-10K chars)
- 20 numbered chapters (01-20) + 前言(prologue) + 跋(epilogue) + 推荐序x2 + 附录x2 + 致谢 + 译者后记 + 版权信息 + 目录
- Chapter numbering: `01　title` format — NOT "第一章"
- Files named sequentially `text00000.html` through `text00060.html`
- Chapter k spans files `text0(18+2k).html` (title) + `text0(19+2k).html` (body)

## Alignment Map

| English | Chinese | Notes |
|---------|---------|-------|
| Ch1 (ONE) | 前言 (text00008) | Prologue — single file in ZH |
| Ch2 (TWO) | 01 (text00010+11) | |
| Ch3 (THREE) | 02 (text00012+13) | |
| ... | ... | |
| Ch21 (TWENTY-ONE) | 20 (text00051+52) | |
| Epilogue | 跋 (text00053) | Single file in ZH |

Key difference: English has 21 numbered chapters + epilogue. Chinese has 前言 + 20 chapters + 跋. The prologue in EN is "Ch1" but in ZH it's "前言" (unnumbered).

## Why extract_chapters.py Failed

1. `detect_chapter_offset()` looks for "CHAPTER 1" — Into Thin Air uses "ONE", so offset detection returns default (1), pointing at the wrong file
2. Header cleanup `re.sub(r"^Born to Run:.*?(?=CHAPTER)")` — doesn't match, header text remains
3. Chinese offset detection looks for "第一章" — this book uses "01　", so it fails
4. Script assumes 1 HTML file = 1 chapter — Chinese book has 2 files per chapter
5. Result: only 1 "chapter" extracted, with wrong content

## Fix: Custom Extraction in execute_code

```python
import zipfile, re
from html.parser import HTMLParser

# Use HTMLToText parser (same as extract_chapters.py)
# Manually map EN chapter files to ZH chapter file pairs
# For ZH: concatenate title_page + body_text files
# Write to chapters/en/chNN.txt and chapters/zh/chNN.txt
```

This approach is fast (~0.5s) and reliable because the mapping is explicit.
