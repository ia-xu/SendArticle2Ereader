# Python Regex Pitfalls in tex2md.py

Two subtle regex bugs encountered during Kimi Linear paper conversion.

## Bug 1: `\|` Empty-String Alternation (P15)

**Symptom:** `_wrap_leaked_math_blocks` wrapped 44 non-math blocks
(`*Kimi Team*`, `---`, blank lines) in `$$`.

**Root cause:** In the `_has_math_content` indicator list:
```python
r'\\|'  # INTENDED: match literal \| (norm symbol)
```

Python regex interprets `\|` as `\` OR empty string (because `|` is
alternation preceded by an escaped backslash that's just `\`).
The empty-string branch matches EVERY position, so `is_actual_math()`
returns True for any input.

**Fix:** Remove `r'\\|'` from the indicator list. Use `r'\\\\|'` if
matching literal backslash-pipe is genuinely needed.

**Verification:** Always test with a known non-math string:
```python
assert not is_actual_math('*Kimi Team*')
assert not is_actual_math('---')
assert is_actual_math(r'\mathbf{S}_t')
```

## Bug 2: `re.escape` + Non-Raw Strings (P16)

**Symptom:** `_strip_twoarg_command(content, '\\\\raisebox')` never matched
`\raisebox{0pt}{\faGithub}` in the content, leaving orphan `{0pt{...}}` patterns.

**Root cause:** The call `_strip_twoarg_command(content, '\\\\raisebox')`
passes the Python string `\\raisebox` (2 backslashes). Inside the method,
`re.escape('\\raisebox')` first interprets the string — `\r` becomes carriage
return (ASCII 13) — then escapes. Result regex matches `\r` (CR) + `aisebox`,
not `\raisebox` (backslash-r).

**Fix:** Use raw string literals in the caller:
```python
# WRONG:
content = self._strip_twoarg_command(content, '\\\\raisebox')

# RIGHT:
content = self._strip_twoarg_command(content, r'\raisebox')
```

The raw string `r'\raisebox'` is a single backslash followed by `raisebox`.
`re.escape` then produces the correct regex `\\raisebox`.

## Bug 3: Processing Order (P17)

**Symptom:** `\raisebox{0pt}{\faGithub}` inside `\footnote{}` in the abstract
was never stripped, leaving `{0pt{}}\,\,\,...` artifacts.

**Root cause:** The conversion pipeline order in `LatexToMarkdown.convert()`:
1. `_process_references` runs → `\footnote{content}` → `(content)`
2. `_cleanup` runs → strips `\raisebox` (but it's already inside `(...)`)

The `\raisebox` inside the footnote content was "baked in" to the footnote
text before `_cleanup` could strip it.

**Fix:** Added `_clean_orphan_dimen_braces()` and `[scale=...]{path}` cleanup
as a final pass in `_cleanup` to handle these orphan brace patterns regardless
of their origin. Also fixed Bug 2 so `_strip_twoarg_command` correctly matches
`\raisebox` when it IS reachable.
