# TikZ Figure Loss — Diagnostic Workflow (Kimi K3 session, v4.0)

## When to use
Paper conversion where `\ref{fig:...}` text appears but the figure image is
missing, or whole sections / the appendix vanish from the MD.

## Quick triage (run on the output MD)
1. `grep -c "TIKZ_FIGURE\|TIKZ_RAW\|TABLE_RAW\|CODE_RAW" paper.md`
   - After Step 3 all should be 0. Before Step 3, TIKZ_FIGURE/TIKZ_RAW markers
     are expected (they are resolved by tikz_placeholder.py).
2. `grep -o "(Figure [0-9]*)" paper.md` vs `grep -o "(Figure [a-z_-]*)" paper.md`
   - `(Figure arch)` style = label-name fallback → the figure's label was never
     recorded or its env was dropped (P35).
3. Compare image count `grep -c "!\[" paper.md` against source figure envs
   `grep -c "begin{figure}" *.tex appendix/*.tex` — a shortfall = dropped figures.
4. Missing appendix? `grep -c "Chat Template\|Contributions" paper.md` — if a
   `# Appendix` heading exists but no content, suspect P37.
5. Raw `\subsection{` in output = P38 (stray `$$` in a caption corrupted math
   pairing, so `_process_inline_commands` never saw the headings).

## Root-cause chain found in Kimi K3 (arXiv 2607.24653)
- 7 TikZ figures (arch, kda-lower-bound, situglu, quantile-balancing, kcp,
  case-study-kernel-optimization, chat-template) were ALL missing from the MD.
- `\ref{fig:arch}` rendered as `Fig.~(Figure arch)`; no TIKZ_FIGURE placeholders survived.
- The one inline-tikz figure (prefix caching, 5-infrastructure.tex:340) existed in
  the user's output only as a manually compiled PNG (timestamp archaeology: created
  10 min before the rest of the run — a separate manual step, not the pipeline).

## Fixes applied (tex2md.py + tikz_placeholder.py)
- P35: `_convert_figure_env` preserves TIKZ_FIGURE placeholders + caption + label,
  records label → figure number in `self.figure_labels`.
- P36: `_is_tikz_figure` rejects document/section files (structural commands).
- P37: `resolve_input` uses `is_file()` + fall-through on read failure.
- P38: `_clean_text_content` protects `$...$` / `$$...$$` before command stripping.
- New: inline tikzpictures in figure envs → `<!-- TIKZ_RAW:N|caption -->` blocks;
  tikz_placeholder.py Phase 3 compiles them → `images/tikz_N.png`.
- New: `\ref{fig:x}` → `(Figure N)`; `\S` → `§`; `~(` → ` (`;
  `\printbibliography[...]` stripped.

## Verification (end-to-end pass)
- tex2md summary `[tex2md] Converted N images, M figures` — M should equal the
  number of figure envs in the source (includegraphics + TikZ + inline TikZ).
- tikz_placeholder tail: `Done: 7/7 TikZ figures resolved, 1/1 TIKZ_RAW blocks resolved`.
- `$$` count even, inline `$` count even (mask `USD($)` first — P34).
- 0 leftover placeholders, 0 raw `\subsection{`.

## Tooling lessons (P26 reinforcement)
- The patch tool corrupts `\r` even inside Python comments (e.g. a comment containing
  `\ref` splits into two lines with a CR byte). Keep `\r`-prefixed words out of any
  patch old/new_string.
- Whole-function edits: replace by LINE RANGE in a fix script
  (`lines[i:j] = new_funcs.split('\n')`) — immune to backslash-count mismatches
  (single vs double backslash in comments/strings caused several failed anchors).
- Inline `python -c` double-escapes backslashes (bash + Python) — write a .py file.
- A fix script that edits `content` in memory and writes only at the end loses all
  earlier edits if a later assert fails — apply + write incrementally, then verify.
