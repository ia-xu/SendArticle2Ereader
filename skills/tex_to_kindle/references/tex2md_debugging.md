# tex2md.py Debugging Notes

Critical bugs found and fixed during initial development. These patterns are
subtle and easy to reintroduce when extending the converter.

## 1. Double-append in search loops (MOST DANGEROUS)

**Affected:** `_replace_braced_command`, `_expand_parameterized_macro`, `_convert_ensuremath`

**Symptom:** Content size explodes exponentially (62K → 47M → 65M chars).
Output file balloons to 100MB+. The entire paper content gets duplicated
thousands of times.

**Root cause:** When `re.search` finds no match, the code did:
```python
if not match:
    result.append(content[pos:])  # BUG: appends remaining content
    break
# ... after loop:
if pos < len(content):
    result.append(content[pos:])  # BUG: appends AGAIN
```

**Fix pattern:** `break` WITHOUT appending. Only append remaining content
ONCE after the loop:
```python
if not match:
    break  # No append here
# ... after loop:
if pos < len(content):
    result.append(content[pos:])
elif not result:
    return content  # No matches at all
```

If you add any new search-and-replace method that walks content with
`re.search` + balanced-brace extraction, copy this pattern exactly.

## 2. Macro word-boundary matching

**Symptom:** `\mathbb{E}` becomes `{{h}}bb{E}` — the `\mat` macro
(from `\newcommand{\mat}[1]{\ensuremath{\bm{#1}}}`) matches inside `\mathbb`.

**Root cause:** `re.escape('\\mat')` matches as a substring of `'\\mathbb'`.
Plain `str.replace` has the same problem.

**Fix:** Add negative lookahead `(?![a-zA-Z])` to the pattern, AND check
that the character before the match position is not a letter:
```python
pattern = re.escape(name) + r'(?![a-zA-Z])'
# ... in the match loop:
if abs_start > 0 and content[abs_start - 1].isalpha():
    search_pos = abs_end
    continue  # Skip, it's a longer command
```

Both checks are needed: lookahead prevents `\mat` matching `\mathbb`,
and the backward check prevents `\vect` matching `\protect` etc.

## 3. Math region corruption by inline commands

**Symptom:** `\theta`, `\pi_θ`, `\mathbb{E}`, `\mathrm{old}` inside
`$...$` get stripped or corrupted. Inline math becomes garbage.

**Root cause:** `_process_inline_commands` processes the entire content
including text inside `$...$` delimiters. Commands like `\textbf`, `\emph`
are fine to process outside math, but `\mathrm`, `\mathcal`, `\mathbb`
must be preserved as LaTeX for latex2mathml.

**Fix:** Protect/restore math regions:
1. Before `_process_inline_commands`: replace all `$...$` and `$$...$$`
   with unique placeholders (`MATHPLACEHOLDER{n}ENDMATH`)
2. Run inline command processing on placeholder-protected content
3. After processing: restore placeholders back to original math text

The `_protect_math` and `_restore_math` methods implement this.
Any new inline command added to `_process_inline_commands` is automatically
safe because it never sees math content.

## 4. Comment-first input resolution

**Symptom:** Paper content is duplicated — every section appears twice.
Figure count doubles (11 unique → 22 listed).

**Root cause:** If comments are stripped AFTER `\input` resolution,
a commented-out line like `% \input{3.related_work}` gets resolved
(including the `\input` part), pulling in duplicate content.

**Fix:** Strip comments BEFORE resolving `\input`:
```python
content = _strip_comments_static(content)  # FIRST
content = project.resolve_input(content)   # SECOND
```

## 5. Cleanup stripping math LaTeX

**Symptom:** Block-level formulas `$$...$$` lose their LaTeX commands.
`$$\mathbb{E}\left[...\right]$$` becomes `$${E}[...]$$`.

**Root cause:** `_cleanup` applies `re.sub(r'\\[a-zA-Z]+\b', '', line)`
to lines without `$`. But a formula like:
```
$$L(\theta) = \hat{\mathbb{E}}_t \left[ ... \right]$$
```
is a single line containing `$$`, which the old check
(`'$' in line and '$$' not in line`) didn't skip.

**Fix:** Skip ANY line containing `$`. Track multi-line `$$...$$` blocks
with an `in_block_math` flag. Only strip stray `\command` patterns from
lines with zero `$` characters.

## 6. KFX conversion of math-heavy papers

**Symptom:** Kindle Previewer 3 reports "internal error" when converting
the EPUB to KFX. EPUB itself is valid.

**Cause:** Complex MathML (matrices, multi-line align, nested fractions)
can trigger Kindle Previewer's converter. This is a known limitation.

**Workaround:** Fall back to EPUB format:
- `send_to_kindle(format="epub")` via MCP
- Or copy EPUB directly to Kindle documents folder
- Kindle natively supports EPUB since firmware 5.x

## Quick diagnostic checklist

If tex2md output looks wrong:

1. **Output size > 1MB for a single paper?** → Double-append bug (check #1)
2. **LaTeX commands in math are corrupted?** → Math protection missing (check #3)
3. **Content is duplicated?** → Comment stripping order (check #4)
4. **Math symbols missing from block formulas?** → Cleanup too aggressive (check #5)
5. **Macros bleed into other commands?** → Word boundary matching (check #2)
