# Worked Example: Born to Run / 天生就会跑

First successful end-to-end merge using this skill. Reference for future runs.

## Source Files

- English: `en2chn/天生就会跑/source/Born to Run ... (Christopher McDougall).epub`
- Chinese: `en2chn/天生就会跑/source/天生就会跑 ... (z-library).epub`

## EPUB Structure

Both books: chapter N (1-indexed) maps to HTML file index N+1 in the extracted chapter array (index 0-1 are front matter). Chapter detection works by scanning for `CHAPTER\s*N` (English) or `第N章` (Chinese).

## Chapters Processed (25-32)

| Ch | EN chars | ZH chars | Notes |
|----|----------|----------|-------|
| 25 | 36K | 12K | Normal |
| 26 | 33K | 11K | Normal |
| 27 | 33K | 11K | Normal |
| 28 | 70K | 22K | SPLIT into 2 halves (~35K each) |
| 29 | 10K | 3K | Normal |
| 30 | 14K | 5K | Normal |
| 31 | 39K | 12K | Normal |
| 32 | 15K | 5K | Normal |

## Subagent Batching

3 batches of 3 subagents each (parallel within batch):
- Batch 1: ch25, ch26, ch27 (~3-5 min)
- Batch 2: ch28 (timeout!), ch29, ch30 → ch28 split into ch28a + ch28b
- Batch 3: ch28a, ch28b, ch31
- Batch 4: ch32 (single)

Total: ~20 min for 8 chapters.

## Annotation Density

~20-60 annotations per chapter depending on content. Chapter 28 (science-heavy) had 60+. Narrative chapters ~20-30.

## Output

- Individual chapters: `markdown/ch25.md` through `ch32.md`
- Merged: `markdown/merged_25-32.md` (490KB)
- KFX conversion: file_id `3411dea0` via tokindle MCP
- Log: `markdown/log.txt`

## Key Patterns

1. Chinese translation is ~3x shorter than English (character compression + some omissions)
2. Chinese restructures paragraphs — subagents must align semantically
3. Book title (`Born to Run:...` / `天生就会跑`) repeats at start of each EPUB chapter — clean with regex
4. `merge_md.py` sorts `ch*.md` alphabetically, so ch25 < ch26 < ... works naturally
