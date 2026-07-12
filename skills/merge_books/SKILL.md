---
name: merge_books
description: "Merge bilingual books (Chinese + English) into interleaved format: Chinese paragraph first with rich vocabulary annotations, then English paragraph with inline word glosses"
version: 2.0.0
author: Hermes Agent
platforms: [windows]
metadata:
  hermes:
    tags: [books, bilingual, kindle, translation, vocabulary]
---

# Merge Bilingual Books

Merge Chinese and English versions of the same book into an interleaved bilingual format: **Chinese paragraph first** with rich inline vocabulary annotations, then the **English paragraph second** with inline glosses for difficult words.

## User Preference (IMPORTANT)

The user explicitly requires **Chinese first, English second**. Do NOT reverse this order. Both sections carry vocabulary annotations:
- Chinese section: `中文（english_word：简短中文解释）` for all moderately-difficult+ words
- English section: `difficult_word(简短中文注释)` for harder words

## Prerequisites

- Two EPUB files (English + Chinese) of the same book
- tokindle MCP server running (for KFX conversion)
- Hermes delegate_task for parallel chapter processing

## Directory Structure

```
book_title/
├── source/
│   ├── english_book.epub
│   └── chinese_book.epub
├── chapters/
│   ├── en/          # extracted English chapter text
│   └── zh/          # extracted Chinese chapter text
├── markdown/
│   ├── ch25.md      # merged bilingual chapter
│   ├── ch26.md
│   ├── ...
│   ├── log.txt      # progress tracking
│   └── merged_book.md  # final combined output
└── chapter_map.json    # chapter alignment metadata
```

## Workflow

### Step 0: Analyze EPUB Structure (ALWAYS DO THIS FIRST)

Every EPUB has different internal structure. Before extraction, you MUST analyze both files to understand:

- How many HTML files exist and which are actual chapters vs front/back matter
- Whether chapters are split across multiple HTML files (VERY common in Chinese EPUBs — each chapter often has a separate title-page file + body-text file)
- What chapter numbering format is used (word numbers like ONE/TWO, digits like 01, Chinese numerals like 第一章, etc.)
- Whether the book has a prologue/epilogue that may or may not map to a numbered chapter

```bash
# Side-by-side comparison
python scripts/analyze_epub.py --en "english.epub" --zh "chinese.epub"
# Or single file
python scripts/analyze_epub.py "one_epub.epub"
```

The output shows every HTML file with its text length and first ~150 chars, making it easy to build the chapter alignment map.

If the generic `extract_chapters.py` fails (wrong chapter count, misaligned content), write a custom extraction in `execute_code` using the structure analysis as a guide. This is often faster than debugging the generic script for a new book.

### Step 1: Extract Chapters

**Option A — Generic script** (works for books with simple structure: one HTML file per chapter, standard numbering):

```bash
python scripts/extract_chapters.py \
  --en "path/to/english.epub" \
  --zh "path/to/chinese.epub" \
  --out "path/to/book_dir" \
  --chapters 25-32   # optional range, default all
```

**Option B — Custom extraction** (for complex structures: multi-file chapters, non-standard numbering, front/back matter mismatches):

Write a Python script in `execute_code` that:
1. Opens both EPUBs as zip files
2. Uses the HTMLToText parser (copy from `extract_chapters.py`)
3. Manually maps chapter numbers to HTML files based on the Step 0 analysis
4. For Chinese EPUBs with split chapters, concatenates title-page + body-text files
5. Writes `chapters/en/chNN.txt` and `chapters/zh/chNN.txt`

Example: Into Thin Air had 21 EN chapters (word-numbered ONE..TWENTY-ONE) + epilogue, while the ZH version had 20 numbered chapters (01..20) + 前言(prologue) + 跋(epilogue), each split into 2 HTML files. The generic script detected only 1 chapter; a custom extraction was needed.

See `references/kfx_conversion_debugging.md` for detailed KFX conversion troubleshooting (multi-chapter failure, md2kfx.py bugs, conversion pipeline internals).

### Step 2: Verify Chapter Alignment

Before merging, spot-check that chapter N in English matches chapter N in Chinese. Read the first 30 lines of each to confirm the content matches. Common alignment patterns:
- EN prologue ↔ ZH 前言/序言, EN epilogue ↔ ZH 跋/后记
- Chapter counts may differ by 1 (prologue counted as ch1 in one version but not the other)
- Chinese translations may add 推荐序 (foreword) and 附录 (appendix) not in the English original

### Step 3: Merge Chapters (Parallel via Subagents)

Launch subagents (up to 3 concurrent via delegate_task) to process chapters. Each subagent:

1. Reads `chapters/en/chNN.txt` and `chapters/zh/chNN.txt`
2. Aligns paragraphs (semantic matching, not line-by-line)
3. Produces interleaved Markdown: **Chinese paragraph first (in blockquote), then English paragraph as plain text**
4. Adds inline annotations:
   - Chinese text: `中文（english_word：简短中文解释）` for CET-4+ and all moderately difficult vocabulary
   - English text: `difficult_word(简短中文注释)` for harder words (CET-6+)
5. Writes output to `markdown/chNN.md`

**Prompt template for subagents** (see `templates/chapter_merge.md`).

**Pre-scan for `$` signs (do this before launching subagents)**:
Run a quick scan of all source `.txt` files to find currency amounts. This lets you give each subagent exact context about which amounts to convert:

```python
import re
for ch in ['ch01', 'ch02', 'ch03']:
    for lang in ['en', 'zh']:
        with open(f"book_dir/chapters/{lang}/{ch}.txt", 'r') as f:
            text = f.read()
        dollars = re.findall(r'.{0,20}\$.{0,20}', text)
        if dollars:
            print(f"{lang}/{ch}: {len(dollars)} dollar signs")
            for d in dollars: print(f"  {d}")
```

Include the found amounts in each subagent's context so it knows exactly which `$N` values to write as `USD($)N`. Verify the output files after merging to confirm zero bare `$` signs remain.

For long chapters (>50K chars), see Step 3a below.

### Step 3a: Long Chapter Splitting (>50K chars)

Chapters over ~50K English chars will cause subagent timeout (600s limit). Split them:

```python
import re
# Split at paragraph boundary nearest 50% mark
paras = re.split(r'\n\s*\n', text)
cumlen, split_idx = 0, 0
for i, p in enumerate(paras):
    cumlen += len(p)
    if cumlen > len(text) * 0.5:
        split_idx = i; break
part_a = '\n\n'.join(paras[:split_idx])
part_b = '\n\n'.join(paras[split_idx:])
# Write as chNNa.txt / chNNb.txt, process each as separate subagent
# Then merge outputs: "## Chapter N\n\n" + chNNa.md + "\n\n" + chNNb.md
```

- Do NOT add chapter headings to split halves — only to the merged result
- Clean up split source files after merging

### Step 4: Merge and Convert

```bash
python scripts/merge_md.py --dir "path/to/book_dir/markdown" --title "书名" --output merged_book.md
```

Then use tokindle MCP to convert to KFX:

```
mcp_tokindle_upload_local_file(file_path="path/to/merged_book.md", title="书名 (中英对照)")
# Wait 2-3 min (chapter-length files) or ~5 min (book-length), then poll:
mcp_tokindle_get_file_info(file_id="...")
# Repeat until status="converted" and has_kfx=true
mcp_tokindle_send_to_kindle(file_id="...")
```

**KFX conversion timing**: Chapter-length files (~10-40KB markdown) take 2-4 min to convert. Book-length files take ~5 min. The "40-60s" estimate only applies to short articles. Always wait at least 120s before first poll to avoid wasted rounds.

**Batch workflow (Strategy A — per-chapter conversion)**:
When converting multiple chapters sequentially, overlap push + upload:
1. Upload ch01, wait for conversion
2. When ch01 is ready: call `send_to_kindle(ch01)` AND `upload_local_file(ch02)` in the same parallel tool call batch
3. Wait for ch02 conversion (it runs in background while ch01 push completes)
4. Repeat: send ch02 + upload ch03 together, etc.

This saves ~5 min total vs fully sequential upload→convert→push for each chapter.

**IMPORTANT — Multi-chapter KFX conversion failure (Pitfall 15)**:

Kindle Previewer 3 fails ("internal error") when converting EPUBs with multiple chapters in a single XHTML file. This affects any merged_book.md with 2+ chapters. Two strategies:

**Strategy A — Convert individual chapters (recommended for KFX)**:
Convert each `chNN.md` separately, push each to Kindle. Chapter-length files (~10-40KB MD) take 2-4 min each; full book-length files take ~5 min. The reader gets one Kindle book per chapter, which is fine for reading.

**Strategy B — Push EPUB instead of KFX**:
EPUB format works on Kindle natively. Use `send_to_kindle(format="epub")` or copy the EPUB directly to the Kindle's documents folder. The MCP `upload_local_file` always generates an EPUB even when KFX fails, so you can fall back to EPUB.

**Strategy C — Push EPUB via direct file copy**:
If the MCP server's conversion thread is dead (Pitfall 13), generate EPUBs manually via the md2kfx pipeline and copy directly:
```python
from src.md2kfx import MarkdownToKFX
converter = MarkdownToKFX(md_path, output_file, title, author)
html = converter.markdown_to_html()
epub = converter.create_epub(html)
# Copy epub to F:\documents\Downloads\Items01\article\
```

### Step 5: Log Progress

Update `markdown/log.txt` after each chapter batch:

```
2026-06-23 ch25 DONE
2026-06-23 ch28 DONE (split into two halves for parallel processing)
2026-06-23 ch30 DONE
```

### Step 6: Symlink Skill (first time only)

If the skill lives outside the Hermes skills directory, create a Windows directory junction:

```bash
cmd //c "mklink /J C:\Users\<user>\AppData\Local\hermes\skills\merge_books D:\path\to\tokindle\skills\merge_books"
```

## Output Format

**Chinese first** (blockquote with rich annotations), then **English** (plain text with word glosses):

```markdown
## Chapter 25

> 中文段落内容...（difficult_word：简短中文解释）...

English paragraph content with difficult_word(简短中文注释)...

> 下一中文段落...

Next English paragraph...
```

- Chapter headings: `## Chapter N` or `## 第N章`
- Chinese text in `> ` blockquotes (comes first, with rich annotations)
- English text as normal paragraphs (comes second, with word glosses)
- Vocabulary annotations:
  - Chinese: `中文（english_word：简短中文解释）` inline
  - English: `difficult_word(简短中文注释)` inline
- Horizontal rules `---` between chapters

## Vocabulary Annotation Rules

### Chinese Section — Aggressive Annotation

Annotate (first occurrence only per chapter):
- CET-4 and above words (四级以上词汇 — broader than before)
- Moderately difficult words (slightly challenging vocabulary that a typical reader might need to look up)
- Idioms and phrasal verbs (习惯用语)
- Slang and colloquialisms (俚语)
- Cultural references needing explanation
- Domain-specific terms (mountaineering, science, etc.)

Format: `中文（english_word：简短中文解释）` — e.g., `跑鞋对双脚的摧残（destructive：破坏性的）`

Do NOT annotate in Chinese section:
- CET-3 and below common words (basic vocabulary)
- Proper nouns already explained in context
- Repeated words (annotate first occurrence only per chapter)

### English Section — Moderate Annotation

Annotate (first occurrence only per chapter):
- CET-6 and above words (六级以上词汇)
- Difficult idioms and phrasal verbs
- Unusual slang or colloquialisms

Format: `difficult_word(简短中文注释)` — e.g., `The weather began to deteriorate(恶化、变坏)`

Do NOT annotate in English section:
- CET-5 and below words
- Proper nouns already clear in context
- Repeated words (already annotated earlier in chapter)

## Log File

`markdown/log.txt` tracks which chapters have been merged, supporting incremental processing across sessions.

## Pitfalls

1. **extract_chapters.py is hardcoded for Born to Run**: The generic script has hardcoded header cleanup regexes (`^Born to Run:.*?` and `^天生就会跑`) and chapter offset detection (`CHAPTER 1` / `第一章`) that only work for that specific book. For any other book, ALWAYS run Step 0 (analyze EPUB) first. If the script produces wrong results (e.g., extracts only 1 chapter), switch to custom extraction (Step 1, Option B).
2. **Chinese EPUBs split chapters across multiple HTML files**: A single Chinese chapter often occupies two files — a short title-page file (with chapter number + epigraph) and a separate body-text file. The generic script treats each HTML file as one chapter, so it misaligns. When writing custom extraction, concatenate the title-page + body files for each chapter.
3. **Chapter numbering formats vary widely**: English EPUBs may use word numbers (ONE, TWO, TWENTY-ONE), digit numbers (Chapter 1), or Roman numerals. Chinese EPUBs may use 第一章, 01, 第1章, or custom formats like `01　title`. The generic offset detector only matches `CHAPTER 1` and `第一章`. Analyze first, then map manually.
4. **Chapter misalignment**: Chinese translations may merge/split chapters, add prologues/epilogues not in the original, or include 推荐序/附录. Always verify alignment by reading opening lines before processing.
5. **Long chapters timeout**: Chapters >50K English chars cause subagent timeout (600s). Use the Step 3a splitting technique — split at paragraph boundary, process halves separately, merge with single heading.
6. **Paragraph alignment**: Translations restructure paragraphs. The LLM must align semantically, not mechanically.
7. **Subagent rate-limit false failures**: When launching 3 parallel delegate_task subagents on glm-5.2, some may hit HTTP 429 on their final summary API call and report status "failed". However, if the `write_file` tool call completed before the rate limit, the output file is actually fine. **Always verify output files by checking existence + reading the first 10-20 lines**, regardless of what the subagent's summary says. Do not re-launch a subagent just because its summary reported failure — check the file first.
8. **Encoding**: Always use UTF-8. EPUB extraction must handle various HTML encodings.
9. **Repeated book headers**: EPUB extraction often includes the book title repeated at the start of each chapter HTML file. Clean with a regex appropriate for the specific book (NOT the hardcoded Born to Run pattern).
10. **Kindle not connected**: `mcp_tokindle_upload_local_file` succeeds even when Kindle is disconnected — conversion is server-side. File waits until `send_to_kindle` is called with device connected.
11. **KFX conversion is asynchronous**: `upload_local_file` returns immediately with `status: "uploaded"` and `has_kfx: false`. Conversion runs in a background thread and takes 2-4 min for chapter-length files, ~5 min for book-length. Poll `get_file_info` until `has_kfx: true` and `status: "converted"` before calling `send_to_kindle` — otherwise you get "KFX 文件不存在".
11. **Currency `$` breaks KFX — use `USD($)` convention**: The `$` symbol triggers LaTeX math mode (`$...$`). Two currency amounts like `$65,000...$2,300` cause the regex to match everything between them as a "formula", generating invalid MathML that crashes Kindle Previewer. **Rule: in generated Markdown, always write currency as `USD($)amount`** — e.g., `$2,300` → `USD($)2,300`. The md2kfx converter recognizes `USD($)` and restores it to `$` in the final output. This is enforced in the chapter_merge template (see templates/chapter_merge.md "Dollar Sign Handling" section).
12. **Binary search for KFX conversion failures**: When Kindle Previewer gives "internal error" with no useful log, binary-search the content: split the source MD at paragraph boundaries, test each half. Narrow from N→N/2→N/4 paragraphs until the trigger is found. This found the currency `$` bug in ~8 iterations.
13. **MCP conversion thread dies if child processes are killed**: If you `taskkill` ebook-convert/calibre-parallel while the MCP background thread is running, the thread dies silently. Solution: restart MCP server, or bypass MCP entirely (see below).
14. **Direct KFX conversion (bypass MCP)**: When MCP conversion is broken, convert directly:
    ```python
    import sys; sys.path.insert(0, "D:/data/anan/projects/tokindle")
    from src.md2kfx import MarkdownToKFX
    converter = MarkdownToKFX(md_path, kfx_path, title="...", author="...")
    result = converter.convert()  # ~5 min per file via calibre+Kindle Previewer
    import shutil; shutil.copy2(kfx_path, "F:/documents/Downloads/Items01/article/BookName.kfx")
    ```
    Each file takes ~5 min (300s for Kindle Previewer CLI). Run in background with `notify_on_complete=True`.

15. **MULTI-CHAPTER MERGED FILES FAIL KFX CONVERSION (critical)**: Kindle Previewer 3 (invoked by calibre's KFX Output plugin) throws "Kindle conversion has encountered an internal error" when converting an EPUB whose single content.xhtml contains multiple chapters merged together. Individual single-chapter files convert fine. This is NOT a file-size issue (Born to Run at 556KB XHTML works; Into Thin Air at 382KB fails). Removing TOC, horizontal rules, footnotes, or fixing anchor IDs does NOT help — the failure is triggered by the multi-chapter content combination itself. See `references/kfx_conversion_debugging.md` for the full debugging trace. Workarounds: (a) convert each chapter individually to KFX and push separately; (b) push EPUB format instead of KFX (`send_to_kindle(format="epub")` — Kindle natively supports EPUB); (c) when using merge_md.py to create batches, keep batches to a single chapter per file.

16. **MCP conversion thread dies when child processes are killed**: The tokindle MCP server runs KFX conversion in a daemon thread that spawns `ebook-convert.exe` and `calibre-parallel.exe`. If those child processes are killed (e.g., via `taskkill /F`), the daemon thread becomes permanently unresponsive — all subsequent `upload_local_file` calls will show `status: "uploaded"` forever and never convert. The MCP server must be restarted to recover. If conversions appear stuck (polling `get_file_info` shows no progress for 2+ minutes), restart the MCP server rather than killing processes.

17. **KFX conversion takes ~5 minutes per file**: Kindle Previewer 3 CLI processing alone takes ~300 seconds per book, on top of calibre's own EPUB processing. Do NOT expect 40-60 second conversion for book-length content — that timing only applies to short articles. For batches, run conversions sequentially (not parallel — parallel conversions compete for resources and all hang).

18. **Debugging KFX conversion failures**: To see Kindle Previewer's detailed logs, add `--show-kpr-logs` to ebook-convert, or look for `log_KPR_CLI.txt` in calibre temp dirs (`%TEMP%/calibre-*/[a-z0-9_]*/[a-z0-9_]*/0000/`). Binary-search the problem: convert single chapters vs merged, remove TOC (`converter.generate_toc_html = lambda items: ''`), remove horizontal rules, check XML well-formedness, compare EPUB structure against a known-good EPUB.
