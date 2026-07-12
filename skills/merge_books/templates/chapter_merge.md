# Chapter Merge Prompt Template

## For Subagent — Single Chapter Merge

You are merging a bilingual book chapter. **Chinese comes FIRST, English comes SECOND.** Both sections carry vocabulary annotations — be generous with annotations.

### Input Files
- English: `{en_file}`
- Chinese: `{zh_file}`
- Output: `{output_file}`

### Instructions

1. Read both files completely
2. Align paragraphs semantically (translations may restructure/split/merge paragraphs)
3. For each aligned pair, output in this order:
   - Chinese paragraph as blockquote (`> ` prefix) with rich inline annotations
   - Blank line
   - English paragraph as plain text with inline word glosses
4. Chapter heading: `## Chapter N` (omit for split halves like ch28a/ch28b)

### Annotation Format — Chinese Section (AGGRESSIVE)

`中文内容（english_word：简短中文解释）`

Annotate ALL moderately-difficult and above words. Be generous — when in doubt, annotate. Target: CET-4+ vocabulary, slightly challenging words, idioms, slang, domain terms.

Examples:
- 跑鞋或许是人类对自己双脚最大的摧残（destructive：破坏性的）
- 灵丹妙药（magic bullet：万能药，解决一切问题的方案）
- 这个计划注定要失败（doomed：注定失败的）
- 连续几周猛烈的咳嗽（violent：猛烈的、剧烈的）
- 在一种惊人的欲望驱使下（propel：推动、驱使）
- 被疾风堆砌起来的积雪（scour：冲刷、侵蚀）

### Annotation Format — English Section (MODERATE)

`difficult_word(简短中文注释)` — inline, right after the word.

Only annotate harder words (CET-6+) and difficult idioms. Keep it readable.

Examples:
- The weather had begun to deteriorate(恶化、变坏)
- I just couldn't summon(鼓起、唤起) the energy to care
- nothing but the most perfect conditions of weather

### What to Annotate

Chinese section — annotate broadly:
- CET-4 and above vocabulary (四级以上单词)
- Any moderately difficult word a typical Chinese reader might need to look up
- Idioms and phrasal verbs (习惯用语)
- Slang and colloquialisms (俚语)
- Cultural references needing explanation
- Domain-specific terms (mountaineering, science, etc.)
- First occurrence only per chapter

English section — annotate selectively:
- CET-6 and above vocabulary (六级以上单词)
- Difficult idioms and phrasal verbs
- Unusual slang or colloquialisms
- First occurrence only per chapter

### What NOT to Annotate

Chinese section: CET-3 and below basic words, proper nouns clear in context
English section: CET-5 and below words, proper nouns clear in context

### Dollar Sign Handling (CRITICAL)

The `$` symbol in Markdown triggers LaTeX math mode (`$...$`). Currency amounts like `$2,300` will break KFX conversion. **Always write currency as `USD($)` instead of bare `$`**:

- `$2,300` → write as `USD($)2,300`
- `$65,000` → write as `USD($)65,000`
- `$10 million` → write as `USD($)10 million`

The KFX converter (md2kfx.py) recognizes the `USD($)` convention and restores it to `$` in the final output. This applies to ALL `$` signs that are NOT math formulas — currency, prices, fees, costs, etc.

### For Long Chapters (>50K chars)

The chapter will be pre-split into chNNa.txt and chNNb.txt. Process each half WITHOUT a chapter heading. The orchestrator merges the two output files with a single `## Chapter N` heading afterward.

### Delegate Task Context Template

When launching via delegate_task, include in context:

```
English file: {en_file}
Chinese file: {zh_file}
Output file: {output_file}

FORMAT: Chinese FIRST (blockquote with rich annotations), then English (plain text with word glosses).

## Chapter N

> 中文段落内容（difficult_word：简短中文解释）...

English paragraph with difficult_word(简短中文注释)...

[annotation rules as above]

INSTRUCTIONS:
1. Read both files completely
2. Align paragraphs semantically
3. Output: Chinese blockquote FIRST (with aggressive annotations), blank line, English paragraph SECOND (with selective annotations)
4. Use `> ` prefix for Chinese text
5. Chinese annotations: annotate CET-4+ and all moderately difficult words, be generous
6. English annotations: annotate CET-6+ words only, format `word(中文注释)`
7. Write merged output to the output file
```
