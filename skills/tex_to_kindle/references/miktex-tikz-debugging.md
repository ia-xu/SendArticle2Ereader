# MiKTeX + TikZ Debugging Reference

Common failure modes and debugging steps for TikZ figure compilation.

## Symptom 1: Blank/1KB PNGs

**Cause**: `\input{{path}}` with double braces in LaTeX preamble.
LaTeX looks for a file literally named `{path}` instead of `path`.

**Fix**: Use single braces: `\input{path}`.

## Symptom 2: Wrong Colors / Misaligned Text

**Cause**: Custom `\definecolor{...}` definitions and TikZ libraries
from the paper's preamble are missing from the standalone wrapper.

**Check**: Read paper's `main.tex` preamble for:
- `\definecolor{brickred}{HTML}{b92622}` etc.
- `\usetikzlibrary{shadows, decorations.text, chains, ...}`

**Fix**: Copy all color definitions and library entries into
`tikz_placeholder.py`'s `TIKZ_PREAMBLE`.

## Symptom 3: LaTeX errors with wrapfigure/figure*/subfigure/adjustbox

**Cause**: These environments are incompatible with `standalone` class.

**Fix**: `tikz_placeholder.py`'s `_extract_figure_body()` strips them.
If a new wrapper appears, add to the regex patterns.

## Symptom 4: Nested braces in \caption (e.g., \subref)

**Cause**: `\caption{(\subref{fig:x}) text}` — simple `re.sub(r'\\caption\{.*?\}', ...)`
stops at first `}` inside `\subref{fig:x}`.

**Fix**: Use `_remove_balanced_command()` with brace-depth counting.

## Debugging Workflow

1. **Isolate the figure**: Copy the `.tex` file to a temp directory
2. **Build wrapper**:
   ```python
   from tikz_placeholder import TIKZ_PREAMBLE, _extract_figure_body
   raw = open('figure.tex').read()
   body = _extract_figure_body(raw)
   doc = TIKZ_PREAMBLE.replace(r'\input{__TEX_PATH__}', body)
   open('wrapper.tex', 'w').write(doc)
   ```
3. **Compile manually**: `pdflatex -interaction=nonstopmode wrapper.tex`
4. **Check log**: `grep "^!" wrapper.log`
5. **Check PDF**: `ls -la wrapper.pdf` — if >10KB, likely OK

## Package Installation

MiKTeX auto-installs missing packages on first compile.
If this fails, install manually via MiKTeX Console or:
```bash
initexmf --admin --set-config-value [MPM]AutoInstall=1
```
