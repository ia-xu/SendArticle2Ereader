r"""
TeX Source → Markdown Converter (v3.0 — Simplified)

Converts arXiv LaTeX source into Markdown, preserving formulas as-is for
LLM agent post-processing.

What this script handles:
  - Multi-file projects via \input{} resolution (comments stripped first)
  - TikZ/pgfplots detection → <!-- TIKZ_FIGURE:path --> placeholders
  - Custom macro expansion (\newcommand, \def, 
enewcommand)
  - Math environments → $$...$$ blocks (LaTeX preserved as-is)
  - \ensuremath{...} → $...$
  - Inline math $...$ protected during command processing
  - Figures: \includegraphics → PNG (PDF→PNG via pymupdf, EPS→PNG via PIL)
  - Tables: tabular → Markdown tables
  - Algorithm blocks: algorithm/algorithmic → code blocks
  - Lists: itemize/enumerate → Markdown lists
  - Citations: \cite → [key], references: 
ef → labels
  - Special chars: \% → %, \$ → USD($)

What it does NOT do (left for LLM agent post-processing):
  - Fix $$ / $ delimiter pairing (stray $$, unpaired $, mispaired blocks)
  - Convert \operatorname→\mathrm, \bm→\boldsymbol for latex2mathml
  - Clean up \textcolor, \colorbox, 
aisebox, \faGithub remnants
  - Handle \begin{aligned} wrapping for alignment formulas
  - Fix text corruption artifacts

Usage:
  python tex2md.py --tex-dir <source_dir> --output <output.md> [--title "..."] [--author "..."]
"""

import os
import re
import sys
import argparse
import shutil
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Tuple


# ─── PDF → PNG Conversion ─────────────────────────────────────────────

def convert_pdf_to_png(pdf_path: Path, output_dir: Path, dpi: int = 200) -> Optional[Path]:
    """Convert a PDF file to PNG using pymupdf (fitz). Returns the PNG path."""
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(pdf_path))
        if len(doc) == 0:
            return None
        page = doc[0]  # First page only (figures are typically single-page)
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        png_name = pdf_path.stem + ".png"
        png_path = output_dir / png_name
        pix.save(str(png_path))
        doc.close()
        print(f"  [PDF→PNG] {pdf_path.name} → {png_name}")
        return png_path
    except ImportError:
        print(f"  [Warning] pymupdf (fitz) not available — cannot convert {pdf_path.name}")
        return None
    except Exception as e:
        print(f"  [Warning] PDF→PNG failed for {pdf_path.name}: {e}")
        return None


# ─── TeX Project Parser ──────────────────────────────────────────────

class TexProject:
    r"""Parses a multi-file TeX project, resolves \input, expands macros."""

    def __init__(self, tex_dir: Path):
        self.tex_dir = tex_dir
        self.macros: Dict[str, Tuple[int, str]] = {}  # name → (num_args, body)
        self.custom_commands: Dict[str, str] = {}      # simple text macros (no args)
        self.main_file: Optional[Path] = None
        self.figures_dir = tex_dir / "figures"
        self.title = ""
        self.authors = ""

    def find_main_file(self) -> Path:
        r"""Find the main .tex file (the one with \documentclass or \begin{document})."""
        tex_files = sorted(self.tex_dir.glob("*.tex"))
        for tf in tex_files:
            try:
                content = tf.read_text(encoding='utf-8', errors='replace')
            except:
                continue
            if '\\documentclass' in content:
                self.main_file = tf
                return tf
        # Fallback: look for main.tex
        for name in ['main.tex', '0.main.tex', 'paper.tex']:
            p = self.tex_dir / name
            if p.exists():
                self.main_file = p
                return p
        if tex_files:
            self.main_file = tex_files[0]
            return tex_files[0]
        raise FileNotFoundError(f"No .tex files found in {self.tex_dir}")

    def resolve_input(self, content: str) -> str:
        r"""Resolve all \input{...} and \include{...} directives."""
        def replace_input(match):
            filename = match.group(1).strip()
            # Try with and without .tex extension
            # NOTE: use is_file() not exists() — a directory named like the
            # file (e.g. `appendix/` vs `appendix.tex`) must not shadow it (P37).
            for candidate in [filename, filename + '.tex']:
                filepath = self.tex_dir / candidate
                if filepath.is_file():
                    try:
                        sub_content = filepath.read_text(encoding='utf-8', errors='replace')
                    except:
                        continue  # try the next candidate
                    if self._is_tikz_figure(sub_content):
                        rel_path = str(filepath.relative_to(self.tex_dir))
                        return f"\n<!-- TIKZ_FIGURE:{rel_path} -->\n"
                    # Recursively resolve nested \input
                    sub_content = self.resolve_input(sub_content)
                    return f"\n{sub_content}\n"
            return f"\n% [File not found: {filename}]\n"

        content = re.sub(r'\\input\{([^}]+)\}', replace_input, content)
        content = re.sub(r'\\include\{([^}]+)\}', replace_input, content)
        return content

    def extract_macros(self, content: str) -> str:
        r"""Extract and remove \newcommand, \renewcommand, \def definitions."""
        # \newcommand{\name}[nargs]{body}  or  \newcommand*{\name}[nargs]{body}
        def extract_newcommand(match, body):
            name = match.group(1)
            nargs_str = match.group(2)
            nargs = int(nargs_str) if nargs_str else 0
            if nargs == 0:
                self.custom_commands[name] = body
            else:
                self.macros[name] = (nargs, body)
            return ""

        # Match \newcommand{\name}[n] — body is balanced braces extracted separately
        content = self._remove_command_defs(
            content, r'\\(?:newcommand|renewcommand)\*?\s*\{(\\[a-zA-Z@]+)\}(?:\[(\d+)\])?',
            extract_newcommand
        )

        # \def\name{body} (simple, no args)
        def extract_def(match, body):
            name = match.group(1)
            self.custom_commands[name] = body
            return ""

        content = self._remove_command_defs(
            content, r'\\def\s*(\\[a-zA-Z@]+)',
            extract_def
        )

        return content

    def _remove_command_defs(self, content: str, pattern: str, callback) -> str:
        """Find command definitions with balanced braces and remove them.
        callback receives (match_obj, body_text) and returns replacement string."""
        result = []
        pos = 0
        for match in re.finditer(pattern, content):
            # Find the brace group after the match
            brace_start = match.end()
            # Skip whitespace
            while brace_start < len(content) and content[brace_start] in ' \t':
                brace_start += 1
            if brace_start < len(content) and content[brace_start] == '{':
                _, end = self._extract_balanced_braces(content, brace_start)
                body_text = content[brace_start + 1:end - 1]
                result.append(content[pos:match.start()])
                result.append(callback(match, body_text))
                pos = end
            else:
                result.append(content[pos:match.start()])
                result.append("")
                pos = match.end()
        result.append(content[pos:])
        return ''.join(result)

    @staticmethod
    def _extract_balanced_braces(s: str, start: int) -> Tuple[int, int]:
        """Extract content between balanced braces. Returns (length, end_pos)."""
        if start >= len(s) or s[start] != '{':
            return 0, start
        depth = 0
        for i in range(start, len(s)):
            if s[i] == '{':
                depth += 1
            elif s[i] == '}':
                depth -= 1
                if depth == 0:
                    return (i - start + 1), (i + 1)
        return (len(s) - start), len(s)

    def expand_macros(self, content: str) -> str:
        """Expand custom macros (simple text substitutions, no args)."""
        # Expand simple macros (no args) — do this iteratively to handle nesting
        # Use word-boundary matching so \mat doesn't match \mathbb
        for _ in range(3):
            changed = False
            for name, body in self.custom_commands.items():
                # name starts with \\, e.g. \\model — add negative lookahead for letters
                pattern = re.escape(name) + r'(?![a-zA-Z])'
                new_content, n = re.subn(pattern, lambda m: body, content)
                if n > 0:
                    content = new_content
                    changed = True
            if not changed:
                break

        # Expand parameterized macros \name{arg1}{arg2}...
        for name, (nargs, body) in self.macros.items():
            content = self._expand_parameterized_macro(content, name, nargs, body)

        # Clean up leftover empty braces from macros like \model{} → SAO{}
        content = re.sub(r'\{\}(?!\s*\{)', '', content)  # Remove empty braces
        # Clean up double spaces left by macro expansion
        content = re.sub(r'  +', ' ', content)

        return content

    @staticmethod
    def _is_tikz_figure(content: str) -> bool:
        """Check if content is a standalone TikZ/pgfplots figure file.

        A standalone figure file contains tikzpicture/axis content but is NOT a
        document/section file. Section files that merely contain one inline
        tikzpicture (e.g. 5-infrastructure.tex with a figure env) must NOT be
        treated as figure files, or the whole section would be replaced by a
        placeholder (P36).
        """
        has_tikz = bool(
            re.search(r'\\begin\{tikzpicture\}', content) or
            re.search(r'\\begin\{axis\}', content) or
            re.search(r'\\pgfdeclareplotmark', content)
        )
        if not has_tikz:
            return False
        # Reject document/section files (structural commands present)
        if re.search(r'\\(section|subsection|subsubsection|chapter|part)\b', content):
            return False
        if re.search(r'\\(begin\{document\}|documentclass|include\{)', content):
            return False
        return True

    @staticmethod
    def _expand_parameterized_macro(content: str, name: str, nargs: int, body: str) -> str:
        """Expand a macro with arguments: \\name{a}{b} → body with #1=a, #2=b.
        Uses word-boundary matching so \\mat does NOT match \\mathbb."""
        pattern = re.escape(name) + r'(?![a-zA-Z])'
        result = []
        pos = 0
        search_pos = 0
        while search_pos < len(content):
            match = re.search(pattern, content[search_pos:])
            if not match:
                break  # No more matches — remaining handled after loop
            abs_start = search_pos + match.start()
            abs_end = search_pos + match.end()
            # Check word boundary: previous char must not be a letter
            if abs_start > 0 and content[abs_start - 1].isalpha():
                search_pos = abs_end
                continue
            result.append(content[pos:abs_start])
            # Extract arguments
            args = []
            arg_pos = abs_end
            for _ in range(nargs):
                while arg_pos < len(content) and content[arg_pos] in ' \t\n':
                    arg_pos += 1
                if arg_pos < len(content) and content[arg_pos] == '{':
                    _, end = TexProject._extract_balanced_braces(content, arg_pos)
                    args.append(content[arg_pos + 1:end - 1])
                    arg_pos = end
                elif arg_pos < len(content):
                    args.append(content[arg_pos])
                    arg_pos += 1
                else:
                    args.append("")
            # Substitute
            expanded = body
            for i, arg in enumerate(args):
                expanded = expanded.replace(f'#{i+1}', arg)
            result.append(expanded)
            pos = arg_pos
            search_pos = arg_pos
        # Append remaining content after the last match (single append)
        if pos < len(content):
            result.append(content[pos:])
        elif not result:
            return content  # No matches found at all
        return ''.join(result)


# ─── LaTeX → Markdown Converter ──────────────────────────────────────

class LatexToMarkdown:
    """Converts merged LaTeX content to clean Markdown."""

    # Map common LaTeX environments to Markdown equivalents
    MATH_ENVS = {'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
                 'eqnarray', 'eqnarray*', 'multline', 'multline*', 'displaymath',
                 'cases', 'split', 'aligned', 'gathered'}
    LIST_ENVS = {'itemize', 'enumerate', 'description'}
    TABLE_ENVS = {'table', 'table*', 'tabular'}
    FIGURE_ENVS = {'figure', 'figure*'}
    CODE_ENVS = {'verbatim', 'lstlisting', 'minted'}
    ALGORITHM_ENVS = {'algorithm', 'algorithm*', 'algorithmic', 'algorithm2e'}
    IGNORE_ENVS = {'comment', 'hide'}

    def __init__(self, tex_project: TexProject, output_dir: Path, images_dir: Path):
        self.project = tex_project
        self.output_dir = output_dir
        self.images_dir = images_dir
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.figure_counter = 0
        self.figure_labels: Dict[str, int] = {}  # label to figure number for refs
        self.table_counter = 0
        self.table_raw_counter = 0
        self.code_raw_counter = 0
        self.tikz_raw_counter = 0
        self.equation_counter = 0
        self.citations: Dict[str, str] = {}  # key → formatted citation text

    def convert(self, content: str) -> str:
        """Main conversion pipeline."""
        # 1. Remove comments
        content = self._strip_comments(content)

        # 2. Extract and remove bibliography
        content = self._handle_bibliography(content)

        # 3. Expand macros
        content = self.project.expand_macros(content)

        # 4. Extract title and authors from \maketitle area
        content = self._extract_title_authors(content)

        # 5. Remove preamble (\documentclass to \begin{document})
        content = self._remove_preamble(content)

        # 6. Convert \ensuremath{...} to $...$ (before math protection)
        content = self._convert_ensuremath(content)

        # 7. Process environments (including math environments → $$...$$)
        content = self._process_environments(content)

        # 8. Protect math regions before inline command processing
        placeholders = {}
        content = self._protect_math(content, placeholders)

        # 9. Process inline commands (non-math)
        content = self._process_inline_commands(content)

        # 10. Restore math regions
        content = self._restore_math(content, placeholders)

        # 11. Process math delimiters and leftover LaTeX
        content = self._process_math(content)
        content = self._process_figures_inline(content)
        content = self._process_references(content)
        content = self._process_special_chars(content)
        content = self._cleanup(content)

        return content

    def _convert_ensuremath(self, content: str) -> str:
        """Convert \\ensuremath{...} to $...$ so math content is properly delimited."""
        result = []
        pos = 0
        idx = 0
        while idx < len(content):
            match = re.search(r'\\ensuremath\s*\{', content[idx:])
            if not match:
                break  # No more matches — remaining handled after loop
            abs_start = idx + match.start()
            brace_start = idx + match.end() - 1
            _, end = TexProject._extract_balanced_braces(content, brace_start)
            inner = content[brace_start + 1:end - 1]
            result.append(content[pos:abs_start])
            result.append(f'${inner}$')
            pos = end
            idx = end
        if pos < len(content):
            result.append(content[pos:])
        elif not result:
            return content
        return ''.join(result)

    def _protect_math(self, content: str, placeholders: dict) -> str:
        """Replace all math regions ($...$, $$...$$) with unique placeholders.
        This prevents inline command processing from corrupting LaTeX math."""
        counter = [0]

        def make_placeholder(math_text: str) -> str:
            key = f"MATHPLACEHOLDER{counter[0]}ENDMATH"
            counter[0] += 1
            placeholders[key] = math_text
            return key

        # Protect $$...$$ first (block math)
        def replace_block_math(match):
            return make_placeholder(match.group(0))

        content = re.sub(r'\$\$.*?\$\$', replace_block_math, content, flags=re.DOTALL)

        # Protect $...$ (inline math) — but not \$ or $ in non-math context
        # Match $...$ where content doesn't span lines and doesn't contain $$
        def replace_inline_math(match):
            return make_placeholder(match.group(0))

        # Inline math: $ followed by non-$, then non-$ content, then $
        # Avoid matching across lines (inline math is typically single-line)
        content = re.sub(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', replace_inline_math, content)

        return content

    def _restore_math(self, content: str, placeholders: dict) -> str:
        """Restore math placeholders back to their original content."""
        for key, math_text in placeholders.items():
            content = content.replace(key, math_text)
        return content

    def _strip_comments(self, content: str) -> str:
        r"""Remove LaTeX comments (% to end of line), preserving escaped \%.

        Also strips \\iffalse...\\fi blocks (conditional compilation that
        comments out content — like HTML comments, the content is excluded).
        """
        # Strip \iffalse...\fi blocks entirely (content is excluded by the author)
        # Use non-greedy match with DOTALL to handle multi-line blocks.
        content = re.sub(r'\\iffalse\b.*?\\fi\b', '', content, flags=re.DOTALL)

        lines = content.split('\n')
        result = []
        for line in lines:
            # Find unescaped %
            i = 0
            while i < len(line):
                if line[i] == '%' and (i == 0 or line[i-1] != '\\'):
                    break
                i += 1
            result.append(line[:i])
        return '\n'.join(result)

    def _handle_bibliography(self, content: str) -> str:
        """Remove \bibliographystyle and \bibliography commands."""
        content = re.sub(r'\\bibliographystyle\s*\{[^}]*\}', '', content)
        content = re.sub(r'\\bibliography\s*\{[^}]*\}', '', content)
        return content

    def _extract_title_authors(self, content: str) -> str:
        """Extract \title and \author for metadata."""
        title_match = re.search(r'\\title\s*\{', content)
        if title_match:
            _, end = TexProject._extract_balanced_braces(content, title_match.end() - 1)
            title = content[title_match.end():end - 1]
            # Clean title
            title = re.sub(r'\\[a-zA-Z]+\s*\{([^}]*)\}', r'\1', title)
            title = title.replace('\\xspace', '').replace('\\model', 'SAO').strip()
            self.project.title = title

        author_match = re.search(r'\\author\s*\{', content)
        if author_match:
            _, end = TexProject._extract_balanced_braces(content, author_match.end() - 1)
            author = content[author_match.end():end - 1]
            # Clean author: remove \thanks, \footnote, affiliations
            author = re.sub(r'\\thanks\s*\{[^}]*\}', '', author)
            author = re.sub(r'\\footnotemark\[[^\]]*\]', '', author)
            author = re.sub(r'\\quad', ' ', author)
            author = re.sub(r'\\\\', ', ', author)
            author = re.sub(r'\s+', ' ', author).strip()
            author = re.sub(r',\s*$', '', author)
            self.project.authors = author

        return content

    def _remove_preamble(self, content: str) -> str:
        r"""Remove everything from \documentclass to \begin{document}."""
        # Find \begin{document}
        doc_start = content.find('\\begin{document}')
        if doc_start != -1:
            content = content[doc_start + len('\\begin{document}'):]
        # Remove \end{document} and everything after
        doc_end = content.find('\\end{document}')
        if doc_end != -1:
            content = content[:doc_end]
        # Remove \maketitle, \appendix
        content = re.sub(r'\\maketitle\s*', '', content)
        content = re.sub(r'\\appendix\s*', '\n\n# Appendix\n\n', content)
        return content

    def _process_environments(self, content: str) -> str:
        r"""Process LaTeX environments (\begin{env}...\end{env})."""
        # Process from innermost to outermost
        max_iterations = 50
        for _ in range(max_iterations):
            # Find the innermost \begin{env}...\end{env}
            match = re.search(r'\\begin\{(\w+\*?)\}', content)
            if not match:
                break
            env_name = match.group(1).rstrip('*')
            env_pattern = re.compile(
                r'\\begin\{' + re.escape(match.group(1)) + r'\}(.*?)\\end\{' + re.escape(match.group(1)) + r'\}',
                re.DOTALL
            )
            env_match = env_pattern.search(content)
            if not env_match:
                # Unmatched environment — skip the \begin
                content = content[:match.start()] + content[match.end():]
                continue

            inner = env_match.group(1)
            env_base = env_name.rstrip('*')

            if env_base in self.IGNORE_ENVS:
                replacement = ""
            elif env_base in self.MATH_ENVS:
                replacement = self._convert_math_env(inner, env_base)
            elif env_base in self.LIST_ENVS:
                replacement = self._convert_list(inner, env_base)
            elif env_base in self.FIGURE_ENVS:
                replacement = self._convert_figure_env(inner)
            elif env_base in self.ALGORITHM_ENVS:
                replacement = self._convert_algorithm_env(inner, env_base)
            elif env_base in self.CODE_ENVS:
                replacement = self._convert_code_env(inner, env_base)
            elif env_base == 'abstract':
                replacement = self._convert_abstract(inner)
            elif env_base == 'center':
                replacement = inner.strip() + '\n'
            elif env_base in ('table', 'table*'):
                replacement = self._convert_table_env(inner)
            elif env_base in ('theorem', 'lemma', 'proposition', 'definition',
                              'corollary', 'remark', 'example', 'proof'):
                replacement = self._convert_theorem(inner, env_base)
            elif env_base == 'tabular':
                replacement = self._convert_tabular(inner)
            else:
                # Unknown environment: keep inner content
                replacement = inner.strip()

            content = content[:env_match.start()] + '\n' + replacement + '\n' + content[env_match.end():]

        return content

    def _convert_math_env(self, inner: str, env_name: str) -> str:
        """Convert math environments to $$...$$ block, preserving LaTeX for latex2mathml."""
        self.equation_counter += 1
        math = inner.strip()
        # Remove \label{...} and \tag{...}
        math = re.sub(r'\\label\s*\{[^}]*\}', '', math)
        math = re.sub(r'\\tag\s*\{[^}]*\}', '', math)
        # For cases/split/aligned/gathered: these are AMS sub-environments
        # that are always nested inside a parent math env (equation/align).
        # The parent already provides $$ wrapping, so we just unpack the
        # inner content. The \\ line breaks preserve alignment structure.
        if env_name in ('cases', 'split', 'aligned', 'gathered'):
            return math
        return f'\n\n$${math}$$\n\n'

    def _convert_list(self, inner: str, env_name: str) -> str:
        """Convert itemize/enumerate to Markdown lists."""
        # Strip optional arguments like [leftmargin=*,itemsep=0pt,...]
        inner = re.sub(r'^\s*\[[^\]]*\]', '', inner)

        items = re.split(r'\\item\b', inner)
        items = [it.strip() for it in items if it.strip()]

        if env_name == 'enumerate':
            lines = []
            for i, item in enumerate(items, 1):
                # Handle nested content
                item = item.replace('\n', '\n  ')
                lines.append(f"{i}. {item}")
            return '\n' + '\n'.join(lines) + '\n'
        elif env_name == 'description':
            lines = []
            for item in items:
                # \item[label] text
                m = re.match(r'\[([^\]]*)\]\s*(.*)', item, re.DOTALL)
                if m:
                    lines.append(f"- **{m.group(1)}**: {m.group(2).strip()}")
                else:
                    lines.append(f"- {item}")
            return '\n' + '\n'.join(lines) + '\n'
        else:  # itemize
            lines = []
            for item in items:
                item = item.replace('\n', '\n  ')
                lines.append(f"- {item}")
            return '\n' + '\n'.join(lines) + '\n'

    def _convert_figure_env(self, inner: str) -> str:
        """Convert figure environment to Markdown image + caption."""
        # Find \includegraphics
        img_match = re.search(
            r'\\includegraphics\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}',
            inner
        )
        if not img_match:
            # Figure contains TikZ placeholder(s) (from \input{figures/*.tex}
            # resolution). Preserve them so tikz_placeholder.py (Step 3) can
            # render them — otherwise the whole figure (image + caption + label)
            # is silently dropped (P35).
            tikz_matches = re.findall(r'<!--\s*TIKZ_FIGURE:([^\s>]+)\s*-->', inner)
            if tikz_matches:
                caption = self._extract_figure_caption(inner)
                label_match = re.search(r'\\label\s*\{([^}]+)\}', inner)
                label = label_match.group(1) if label_match else ''
                self.figure_counter += 1
                if label:
                    self.figure_labels[label] = self.figure_counter
                result = ''.join(f'\n\n<!-- TIKZ_FIGURE:{t} -->\n' for t in tikz_matches)
                if caption:
                    result += f'\n*Figure {self.figure_counter}: {caption}*\n'
                return result + '\n'
            # Inline tikzpicture/axis (not via \input) inside figure env —
            # render via TIKZ_RAW block (tikz_placeholder.py Phase 3).
            if re.search(r'\\begin\{(tikzpicture|axis)\}', inner):
                self.tikz_raw_counter += 1
                n = self.tikz_raw_counter
                caption = self._extract_figure_caption(inner)
                label_match = re.search(r'\\label\s*\{([^}]+)\}', inner)
                label = label_match.group(1) if label_match else ''
                self.figure_counter += 1
                if label:
                    self.figure_labels[label] = self.figure_counter
                raw = inner.strip()
                raw = raw.replace('\\', '\\LATEXBS')
                result = (
                    f'\n<!-- TIKZ_RAW:{n}|{caption} -->\n'
                    f'{raw}\n'
                    f'<!-- /TIKZ_RAW:{n} -->\n'
                )
                if caption:
                    result += f'\n*Figure {self.figure_counter}: {caption}*\n'
                return result + '\n'
            # Check if this figure contains code listings (minted/lstlisting/verbatim)
            # instead of images. These need image-based rendering.
            if re.search(r'\\begin\{(minted|lstlisting|verbatim)\}', inner):
                self.code_raw_counter += 1
                n = self.code_raw_counter
                caption = self._extract_table_caption(inner)  # reuse caption extractor
                raw = inner.strip()
                raw = raw.replace('\\', '\\LATEXBS')
                return (
                    f'\n<!-- CODE_RAW:{n}|{caption} -->\n'
                    f'{raw}\n'
                    f'<!-- /CODE_RAW:{n} -->\n'
                )
            return ''  # No image, TikZ, or code found

        img_path = img_match.group(2)
        img_options = img_match.group(1) or ""

        # Resolve image path
        md_img = self._resolve_image(img_path)

        if not md_img:
            return ''

        # Find \caption
        caption = self._extract_figure_caption(inner)

        # Find \label
        label_match = re.search(r'\\label\s*\{([^}]+)\}', inner)
        label = label_match.group(1) if label_match else ''

        self.figure_counter += 1
        if label:
            self.figure_labels[label] = self.figure_counter
        result = f'\n\n![Figure {self.figure_counter}: {caption}]({md_img})\n\n'
        if caption:
            result += f'*Figure {self.figure_counter}: {caption}*\n\n'
        return result

    def _extract_figure_caption(self, inner: str) -> str:
        """Extract and clean \\caption{...} from figure env inner content."""
        cap_match = re.search(r'\\caption\s*\{', inner)
        if not cap_match:
            return ''
        _, end = TexProject._extract_balanced_braces(inner, cap_match.end() - 1)
        return self._clean_text_content(inner[cap_match.end():end - 1])

    def _resolve_image(self, img_path: str) -> str:
        """Resolve an image path and convert PDF to PNG if needed."""
        # Remove leading ./
        img_path = img_path.lstrip('./')

        # Try to find the file
        search_paths = [
            self.project.tex_dir / img_path,
            self.project.figures_dir / Path(img_path).name,
            self.project.tex_dir / 'figures' / img_path,
        ]

        # Try with extensions
        for base_path in search_paths:
            if base_path.exists():
                return self._convert_image_for_md(base_path)
            # Try common extensions
            for ext in ['.pdf', '.png', '.jpg', '.jpeg', '.eps']:
                p = base_path.with_suffix(ext)
                if p.exists():
                    return self._convert_image_for_md(p)

        print(f"  [Warning] Image not found: {img_path}")
        return ''

    def _convert_image_for_md(self, src_path: Path) -> str:
        """Convert image to Kindle-compatible format, return relative path."""
        ext = src_path.suffix.lower()

        if ext == '.pdf':
            # Convert PDF → PNG
            png_path = convert_pdf_to_png(src_path, self.images_dir)
            if png_path:
                return f"images/{png_path.name}"
            return ''

        if ext in ('.png', '.jpg', '.jpeg', '.gif'):
            dest_path = self.images_dir / src_path.name
            if not dest_path.exists():
                shutil.copy2(src_path, dest_path)
            return f"images/{src_path.name}"

        if ext == '.eps':
            # Try converting EPS → PNG via PIL (may not work)
            try:
                from PIL import Image
                img = Image.open(src_path)
                png_name = src_path.stem + '.png'
                img.save(self.images_dir / png_name, 'PNG')
                return f"images/{png_name}"
            except:
                print(f"  [Warning] Cannot convert EPS: {src_path.name}")
                return ''

        print(f"  [Warning] Unsupported image format: {ext}")
        return ''

    def _convert_tabular(self, inner: str) -> str:
        """Convert tabular environment to Markdown table."""
        # Parse column specification
        lines = inner.strip().split('\\\\')
        rows = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('\\toprule') or line.startswith('\\midrule') or line.startswith('\\bottomrule'):
                # Extract any data before the rule
                if line in ('\\toprule', '\\midrule', '\\bottomrule'):
                    continue
                # Sometimes there's data + rule on same line
                line = re.sub(r'\\(toprule|midrule|bottomrule|hline|cline\{[^}]*\})', '', line).strip()
                if not line:
                    continue
            # Remove \rowcolor{...}
            line = re.sub(r'\\rowcolor\s*\{[^}]*\}', '', line)
            # Remove \multicolumn/\multirow — extract content
            line = re.sub(r'\\multicolumn\s*\{[^}]*\}\s*\{[^}]*\}\s*\{([^}]*)\}', r'\1', line)
            line = re.sub(r'\\multirow\s*\{[^}]*\}\s*\{[^}]*\}\s*\{([^}]*)\}', r'\1', line)
            # Remove \setlength{...}
            line = re.sub(r'\\setlength\s*\{[^}]*\}\s*\{[^}]*\}', '', line)
            # Split by & (but not inside braces)
            cells = self._split_table_cells(line)
            cells = [self._clean_text_content(c).strip() for c in cells]
            if any(c for c in cells):
                rows.append(cells)

        if not rows:
            return ''

        # Build Markdown table
        # Normalize column count
        max_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < max_cols:
                r.append('')

        md_lines = []
        # First row is header
        header = rows[0]
        md_lines.append('| ' + ' | '.join(header) + ' |')
        md_lines.append('| ' + ' | '.join(['---'] * max_cols) + '|')
        for row in rows[1:]:
            md_lines.append('| ' + ' | '.join(row) + ' |')

        return '\n' + '\n'.join(md_lines) + '\n'

    @staticmethod
    def _split_table_cells(line: str) -> List[str]:
        """Split a table row by &, respecting brace nesting."""
        cells = []
        current = []
        depth = 0
        for char in line:
            if char == '{':
                depth += 1
                current.append(char)
            elif char == '}':
                depth -= 1
                current.append(char)
            elif char == '&' and depth == 0:
                cells.append(''.join(current))
                current = []
            else:
                current.append(char)
        cells.append(''.join(current))
        return cells

    def _convert_table_env(self, inner: str) -> str:
        """Handle table environment. Complex tables → raw LaTeX blocks
        for image rendering; simple tables → pass through for tabular.
        """
        # Find tabular spec inside inner content (balanced-brace matching)
        tab_start = re.search(r'\\begin\{tabular\}\{', inner)
        if tab_start:
            spec_start = tab_start.end() - 1  # position of {
            _, spec_end = TexProject._extract_balanced_braces(inner, spec_start)
            spec = inner[tab_start.end():spec_end - 1]
            # Complex column specs: @{}, >{}, !{}
            if any(c in spec for c in '@>!'):
                self.table_raw_counter += 1
                n = self.table_raw_counter
                caption = self._extract_table_caption(inner)
                # Escape all backslash-commands so subsequent tex2md steps
                # (process_inline_commands, cleanup) don't mangle them.
                # The table_renderer script restores them before compiling.
                raw = inner.strip()
                raw = raw.replace('\\', '\\LATEXBS')
                return (
                    f'\n<!-- TABLE_RAW:{n}|{caption} -->\n'
                    f'{raw}\n'
                    f'<!-- /TABLE_RAW:{n} -->\n'
                )

        # Simple table — let inner content (tabular) be processed normally
        return inner

    def _extract_table_caption(self, inner: str) -> str:
        """Extract caption text from table inner content."""
        cap_match = re.search(r'\\caption\s*\{', inner)
        if cap_match:
            caption_start = cap_match.end() - 1  # position of {
            _, end = TexProject._extract_balanced_braces(inner, caption_start)
            caption = inner[cap_match.end():end - 1]
            # Strip \\label{...} from caption
            caption = re.sub(r'\s*\\label\s*\{[^}]*\}', '', caption)
            caption = self._clean_text_content(caption)
            return caption.strip()
        return ''


    def _convert_algorithm_env(self, inner: str, env_name: str) -> str:
        algo_text = inner.strip()

        # Convert algorithmic commands to readable pseudocode
        algo_text = re.sub(r'\\State\s+', '', algo_text)
        algo_text = re.sub(r'\\If\s*\{([^}]*)\}', r'if \1 then', algo_text)
        algo_text = re.sub(r'\\ElsIf\s*\{([^}]*)\}', r'else if \1 then', algo_text)
        algo_text = re.sub(r'\\Else', 'else', algo_text)
        algo_text = re.sub(r'\\For\s*\{([^}]*)\}', r'for \1 do', algo_text)
        algo_text = re.sub(r'\\ForAll\s*\{([^}]*)\}', r'for all \1 do', algo_text)
        algo_text = re.sub(r'\\While\s*\{([^}]*)\}', r'while \1 do', algo_text)
        algo_text = re.sub(r'\\Repeat', 'repeat', algo_text)
        algo_text = re.sub(r'\\Until\s*\{([^}]*)\}', r'until \1', algo_text)
        algo_text = re.sub(r'\\Return\s*', 'return ', algo_text)
        algo_text = re.sub(r'\\EndIf', 'end if', algo_text)
        algo_text = re.sub(r'\\EndFor', 'end for', algo_text)
        algo_text = re.sub(r'\\EndWhile', 'end while', algo_text)
        algo_text = re.sub(r'\\Procedure\s*\{([^}]*)\}\s*\{([^}]*)\}', r'procedure \1(\2)', algo_text)
        algo_text = re.sub(r'\\EndProcedure', 'end procedure', algo_text)
        algo_text = re.sub(r'\\Require\s*\{([^}]*)\}', r'Input: \1', algo_text)
        algo_text = re.sub(r'\\Ensure\s*\{([^}]*)\}', r'Output: \1', algo_text)
        algo_text = re.sub(r'\\Comment\s*\{([^}]*)\}', r'  // \1', algo_text)
        algo_text = re.sub(r'\\textbf\s*\{([^}]*)\}', r'\1', algo_text)
        algo_text = re.sub(r'\\Call\s*\{([^}]*)\}\s*\{([^}]*)\}', r'\1(\2)', algo_text)

        return f'\n\n```\n{algo_text}\n```\n\n'

    def _convert_code_env(self, inner: str, env_name: str) -> str:
        """Convert verbatim/lstlisting/minted to code block."""
        lang = ''
        if env_name == 'lstlisting':
            # Try to extract language
            lang_match = re.search(r'language\s*=\s*(\w+)', inner)
            if lang_match:
                lang = lang_match.group(1).lower()
        elif env_name == 'minted':
            lang_match = re.search(r'\\begin\{minted\}\s*\{(\w+)\}', inner)
            if lang_match:
                lang = lang_match.group(1).lower()

        code = inner.strip()
        return f'\n\n```{lang}\n{code}\n```\n\n'

    def _convert_abstract(self, inner: str) -> str:
        """Convert abstract environment."""
        text = self._clean_text_content(inner.strip())
        return f'\n\n## Abstract\n\n{text}\n\n'

    def _convert_theorem(self, inner: str, env_name: str) -> str:
        """Convert theorem-like environments."""
        labels = {
            'theorem': 'Theorem',
            'lemma': 'Lemma',
            'proposition': 'Proposition',
            'definition': 'Definition',
            'corollary': 'Corollary',
            'remark': 'Remark',
            'example': 'Example',
            'proof': 'Proof',
        }
        label = labels.get(env_name, env_name.capitalize())
        text = self._clean_text_content(inner.strip())
        if env_name == 'proof':
            return f'\n\n*Proof:* {text} □\n\n'
        return f'\n\n**{label}.** {text}\n\n'

    def _process_inline_commands(self, content: str) -> str:
        """Convert inline LaTeX commands to Markdown."""
        # Sections
        content = re.sub(r'\\section\s*\*?\s*\{([^}]*)\}', lambda m: f'\n\n## {self._clean_text_content(m.group(1))}\n\n', content)
        content = re.sub(r'\\subsection\s*\*?\s*\{([^}]*)\}', lambda m: f'\n\n### {self._clean_text_content(m.group(1))}\n\n', content)
        content = re.sub(r'\\subsubsection\s*\*?\s*\{([^}]*)\}', lambda m: f'\n\n#### {self._clean_text_content(m.group(1))}\n\n', content)
        content = re.sub(r'\\paragraph\s*\*?\s*\{([^}]*)\}', lambda m: f'\n\n##### {self._clean_text_content(m.group(1))}\n\n', content)
        content = re.sub(r'\\subparagraph\s*\*?\s*\{([^}]*)\}', lambda m: f'\n\n##### {self._clean_text_content(m.group(1))}\n\n', content)

        # Text formatting
        content = self._replace_braced_command('textbf', content, lambda s: f'**{s}**')
        content = self._replace_braced_command('textit', content, lambda s: f'*{s}*')
        content = self._replace_braced_command('emph', content, lambda s: f'*{s}*')
        content = self._replace_braced_command('underline', content, lambda s: s)
        content = self._replace_braced_command('texttt', content, lambda s: f'`{s}`')
        content = self._replace_braced_command('textsc', content, lambda s: s.upper())
        # NOTE: \mathrm, \mathcal, \mathbf, \mathbb, \text, \bm, \operatorname
        # are NOT processed here — they are LaTeX math commands kept as-is
        # inside $...$ for latex2mathml conversion by md2kfx.

        # \para{...} and \vpara{...} (common custom command for paragraph headers)
        content = self._replace_braced_command('para', content, lambda s: f'\n\n**{s}** ')
        content = self._replace_braced_command('vpara', content, lambda s: f'\n\n**{s}** ')

        # No-arg commands
        content = content.replace('\\xspace', ' ')
        content = content.replace('\\noindent', '')
        content = content.replace('\\indent', '')
        content = content.replace('\\small', '')
        content = content.replace('\\footnotesize', '')
        content = content.replace('\\large', '')
        content = content.replace('\\Large', '')
        content = content.replace('\\centering', '')
        content = content.replace('\\normalsize', '')
        content = content.replace('\\sloppy', '')
        content = content.replace('\\flushleft', '')
        content = content.replace('\\flushright', '')
        content = content.replace('\\hfill', ' ')
        content = content.replace('\\vspace{', '\\vspace{')  # keep for later removal
        content = re.sub(r'\\vspace\s*\{[^}]*\}', '', content)
        content = re.sub(r'\\vspace\s*[\d\w]+', '', content)
        content = re.sub(r'\\hspace\s*\{[^}]*\}', ' ', content)
        content = re.sub(r'\\setlength\s*\{[^}]*\}\s*\{[^}]*\}', '', content)
        content = re.sub(r'\\label\s*\{[^}]*\}', '', content)
        content = re.sub(r'\\caption\s*\{([^}]*)\}', r'\n*\1*\n', content)

        # Line breaks and spacing
        content = re.sub(r'\\\\\s*', '\n', content)
        content = re.sub(r'\\newline', '\n', content)
        content = re.sub(r'\\linebreak', '\n', content)
        content = re.sub(r'\\par\b', '\n\n', content)

        # \url{...} → just the URL
        content = re.sub(r'\\url\s*\{([^}]*)\}', r'\1', content)

        # \usepackage, \documentclass etc (should be gone, but just in case)
        content = re.sub(r'\\usepackage(\[[^\]]*\])?\s*\{[^}]*\}', '', content)
        content = re.sub(r'\\documentclass(\[[^\]]*\])?\s*\{[^}]*\}', '', content)

        # Remove remaining \begin{...} \end{...} for unknown envs
        content = re.sub(r'\\begin\{[^}]*\}(\[[^\]]*\])?', '', content)
        content = re.sub(r'\\end\{[^}]*\}', '', content)

        # Remove \toprule, \midrule, \bottomrule, \hline, \cmidrule (stragglers)
        content = re.sub(r'\\(toprule|midrule|bottomrule|hline|cmidrule(\[[^\]]*\])?)\b', '', content)
        content = re.sub(r'\\rowcolor\s*\{[^}]*\}', '', content)

        # Remove stray setup commands (2 or 3 args)
        content = re.sub(r'\\newenvironment\s*\{[^}]*\}\s*\{[^}]*\}(\s*\{[^}]*\})?', '', content)
        content = re.sub(r'\\captionsetup\s*\{[^}]*\}', '', content)
        # Remove \setminted{...} blocks (multi-line minted configs)
        content = re.sub(r'\\setminted\s*\{[^}]*\}', '', content)
        # Fix \string@ → @ (LaTeX internal command artifact)
        content = content.replace('\\string@', '@')

        return content

    def _replace_braced_command(self, cmd: str, content: str, transform) -> str:
        """Replace \\cmd{content} with transform(content), handling nested braces."""
        pattern = '\\' + cmd
        result = []
        pos = 0
        search_pos = 0
        while search_pos < len(content):
            idx = content.find(pattern, search_pos)
            if idx == -1:
                break  # No more matches — remaining content handled after loop
            after = idx + len(pattern)
            if after < len(content) and content[after] not in ' \t{*':
                search_pos = after
                continue
            brace_pos = after
            if brace_pos < len(content) and content[brace_pos] == '*':
                brace_pos += 1
            while brace_pos < len(content) and content[brace_pos] in ' \t':
                brace_pos += 1
            if brace_pos < len(content) and content[brace_pos] == '{':
                _, end = TexProject._extract_balanced_braces(content, brace_pos)
                inner = content[brace_pos + 1:end - 1]
                result.append(content[pos:idx])
                result.append(transform(inner))
                pos = end
                search_pos = end
            else:
                search_pos = after
        # Append remaining content after the last match
        if pos < len(content):
            result.append(content[pos:])
        elif not result:
            return content  # No matches found, return original
        return ''.join(result)

    def _process_math(self, content: str) -> str:
        """Ensure math formulas are properly delimited."""
        # \( ... \) → $ ... $
        # Use (?<!\\) lookbehind so we match single-backslash \( \) (inline math)
        # but NOT \\( or \\) which are LaTeX line breaks with optional args.
        content = re.sub(r'(?<!\\)\\\(\s*', '$', content)
        content = re.sub(r'\s*(?<!\\)\\\)', '$', content)
        # \[ ... \] → $$ ... $$
        # Same lookbehind: match \[ (display math) but NOT \\[ (line break + opt arg).
        content = re.sub(r'(?<!\\)\\\[\s*', '$$', content)
        content = re.sub(r'\s*(?<!\\)\\\]', '$$', content)
        # \displaystyle → just remove (keep content)
        content = content.replace('\\displaystyle', ' ')

        # Convert latex2mathml-unsupported commands (deterministic)
        content = content.replace('\\operatorname', '\\mathrm')
        content = content.replace('\\bm{', '\\boldsymbol{')
        # Also handle \bm x (single-char, no braces) → \boldsymbol{x}
        content = re.sub(r'\\bm\s+([a-zA-Z])', r'\\boldsymbol{\1}', content)
        # Remove \tag{...} from formulas
        content = re.sub(r'\\tag\s*\{[^}]*\}', '', content)
        # Common math commands that need cleanup
        content = re.sub(r'\\\\quad', lambda m: ' \\\\quad ', content)
        # Fix: _process_special_chars converts \$ to USD($), but sometimes
        # the closing $$ of a display math block gets treated as escaped $.
        # This wrecks $$ pairing. Restore the intended $$.
        content = content.replace('\\USD($)$', '$$')
        # Strip custom color macros that survive macro expansion
        # (e.g. \brickred{...}, \midnightblue{...}, \white{...})
        for cmd in ['brickred', 'midnightblue', 'white', 'kimiblue']:
            content = re.sub(
                r'\\' + cmd + r'\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
                r'\1', content
            )

        return content

    def _process_figures_inline(self, content: str) -> str:
        r"""Process standalone \includegraphics outside figure environments."""
        def replace_includegraphics(match):
            img_path = match.group(2)
            md_img = self._resolve_image(img_path)
            if md_img:
                self.figure_counter += 1
                return f'\n\n![Figure {self.figure_counter}]({md_img})\n\n'
            return ''

        content = re.sub(
            r'\\includegraphics\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}',
            replace_includegraphics,
            content
        )
        return content

    def _process_references(self, content: str) -> str:
        """Convert citations and references."""
        # \citep and \parencite → [key1, key2]
        content = re.sub(r'\\(?:citep?|parencite)\s*\{([^}]*)\}', lambda m: f'[{m.group(1)}]', content)
        content = re.sub(r'\\citeauthor\s*\{([^}]*)\}', lambda m: f'[{m.group(1)}]', content)
        content = re.sub(r'\\citeyear\s*\{([^}]*)\}', lambda m: f'[{m.group(1)}]', content)
        # \ref{label} → (Figure N) using recorded figure numbers when available
        def _ref_replacement(label: str) -> str:
            if label in self.figure_labels:
                return f'(Figure {self.figure_labels[label]})'
            if label.startswith('fig:'):
                return f'(Figure {label[4:]})'
            if label.startswith('tab:'):
                return f'(Table {label[4:]})'
            if label.startswith('eq:'):
                return f'(Equation {label[4:]})'
            return f'({label})'
        content = re.sub(r'\\ref\s*\{([^}]*)\}',
                         lambda m: _ref_replacement(m.group(1)),
                         content)
        # LaTeX ~ (non-breaking space) before a ref paren → plain space
        content = re.sub(r'~(?=\()', ' ', content)
        # \eqref{label} → (Equation N)
        content = re.sub(r'\\eqref\s*\{([^}]*)\}',
                         lambda m: f'(Equation {m.group(1)})', content)
        # \footnote{...} → (... ) in parentheses
        content = self._replace_braced_command('footnote', content, lambda s: f' ({s})')
        # \thanks{...} → remove
        content = self._replace_braced_command('thanks', content, lambda s: '')
        content = re.sub(r'\\footnotemark(?:\[[^\]]*\])?', '', content)
        content = re.sub(r'\\footnotetext\s*\{[^}]*\}', '', content)
        return content

    def _process_special_chars(self, content: str) -> str:
        """Convert LaTeX text-level special characters.

        IMPORTANT: Do NOT convert math LaTeX commands (\\alpha, \\theta, etc.)
        to unicode. Those stay as LaTeX inside $...$ for latex2mathml conversion
        by the md2kfx pipeline. Only handle text-level escapes here.
        """
        # Text-level escapes (outside math)
        replacements = {
            '\\%': '%',
            '\\$': 'USD($)',
            '\\&': '&',
            '\\#': '#',
            '\\_': '_',
            '\\{': '{',
            '\\}': '}',
            '\\~': '~',
            '\\S': '§',
            '\\ldots': '...',
            '\\dots': '...',
        }
        for latex, char in replacements.items():
            content = content.replace(latex, char)

        # Remove \\printbibliography / \\bibliography leftovers
        content = re.sub(r'\\printbibliography(?:\[[^\]]*\])?', '', content)
        content = re.sub(r'\\bibliography(?:\[[^\]]*\])?\s*\{[^}]*\}', '', content)

        # Remove \newpage, \clearpage, \pagebreak
        content = re.sub(r'\\(newpage|clearpage|pagebreak)\b', '', content)

        return content

    def _clean_text_content(self, text: str) -> str:
        """Clean up text content (for captions, titles, etc.).

        Math regions ($...$, $$...$$) are protected first so command-stripping
        does not mangle them (e.g. $\boldsymbol{w}$ must not become $$, which
        would break $$ pairing across the whole document — P38).
        """
        math_placeholders = {}
        counter = [0]

        def protect_math(match):
            key = f'__MATHCLEAN{counter[0]}__'
            counter[0] += 1
            math_placeholders[key] = match.group(0)
            return key

        text = re.sub(r'\$\$.*?\$\$', protect_math, text, flags=re.DOTALL)
        text = re.sub(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', protect_math, text)

        text = re.sub(r'\\textbf\s*\{([^}]*)\}', r'**\1**', text)
        text = re.sub(r'\\textit\s*\{([^}]*)\}', r'*\1*', text)
        text = re.sub(r'\\emph\s*\{([^}]*)\}', r'*\1*', text)
        text = re.sub(r'\\texttt\s*\{([^}]*)\}', r'`\1`', text)
        text = re.sub(r'\\citep?\s*\{([^}]*)\}', r'[\1]', text)
        text = re.sub(r'\\ref\s*\{([^}]*)\}', r'\1', text)
        text = re.sub(r'\\label\s*\{[^}]*\}', '', text)
        text = re.sub(r'\\xspace\s*', ' ', text)
        text = re.sub(r'\\[a-zA-Z]+\s*\{([^}]*)\}', r'\1', text)  # Generic: \cmd{x} → x
        text = text.replace('\\xspace', ' ')
        text = re.sub(r'\\[a-zA-Z]+', '', text)  # Remove remaining commands

        for key, val in math_placeholders.items():
            text = text.replace(key, val)

        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _cleanup(self, content: str) -> str:
        """Final cleanup of the Markdown output."""
        # Remove empty $$...$$ blocks (from commented-out equations)
        content = re.sub(r'\$\$\s*\$\$', '', content)

        # Strip \textcolor{color}{content} -> content (balanced braces)
        content = self._strip_twoarg_command(content, r'\textcolor')
        # Strip \colorbox{color}{content} -> content
        content = self._strip_twoarg_command(content, r'\colorbox')
        # Strip \raisebox{dimen}{content} -> content
        content = self._strip_twoarg_command(content, r'\raisebox')

        # Remove fontawesome icons
        content = re.sub(r'\\fa[A-Z][a-zA-Z]*\b', '', content)

        # Clean up orphan raisebox dimen remnants {0pt{...}} -> ...
        # These appear after raisebox{0pt}{X} is stripped to {0pt{X}}
        content = self._clean_orphan_dimen_braces(content)

        # Clean up [scale=...]{path} remnants from \includegraphics in \raisebox
        content = re.sub(r'\[[^\]]*scale=[^\]]*\]\s*\{[^}]*\}', '', content)

        # Remove excessive blank lines
        content = re.sub(r'\n{4,}', '\n\n\n', content)
        # Remove trailing whitespace on lines
        content = re.sub(r' +\n', '\n', content)
        # Remove empty table rows
        content = re.sub(r'\| \| \|', '|  |  |', content)
        # Remove \newpage, \clearpage, \pagebreak
        content = re.sub(r'\\(newpage|clearpage|pagebreak)\b', '', content)

        # Detect and wrap leaked LaTeX math blocks (lines of pure math
        # that lost their $$ wrappers during conversion).
        content = self._wrap_leaked_math_blocks(content)

        # Strip orphan includegraphics option blocks like {width=1\columnwidth}
        content = re.sub(r'\{width=[^}]*\}', '', content)

        return content.strip()
    @staticmethod
    def _strip_twoarg_command(content: str, cmd: str) -> str:
        """Remove \\cmd{arg1}{arg2} from content, keeping arg2 only.
        Uses balanced brace matching for nested braces in arg2."""
        result = []
        pos = 0
        while True:
            m = re.search(re.escape(cmd) + r'\s*\{[^}]*\}\s*\{', content[pos:])
            if not m:
                break
            abs_start = pos + m.start()
            # Position of the second '{' (start of arg2)
            brace2_start = pos + m.end() - 1
            # Find matching '}' for arg2
            depth = 0
            end = brace2_start
            for i in range(brace2_start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            inner = content[brace2_start + 1:end - 1]
            result.append(content[pos:abs_start])
            result.append(inner)
            pos = end
        result.append(content[pos:])
        return ''.join(result)

    @staticmethod
    def _clean_orphan_dimen_braces(content: str) -> str:
        """Clean {dimen{inner}} → inner after raisebox stripping.
        Also handles {dimen{}} (empty inner) and {dimen{text}} patterns."""
        # First pass: {Npt{inner}} or {-Npt{inner}} or {N.Npt{inner}} or {Npt{}} 
        pattern = r'\{[0-9.-]+pt\{'
        result = []
        pos = 0
        for m in re.finditer(pattern, content):
            abs_start = m.start()
            brace1_pos = abs_start  # position of first '{'
            # Find matching '}' for first brace (the dimen arg)
            depth = 0
            end1 = brace1_pos
            for i in range(brace1_pos, len(content)):
                if content[i] == '{': depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end1 = i + 1
                        break
            # The content between dimen's content and its closing is the inner
            # Structure: {dimen{inner}} → find matching }} 
            # end1 is after first '}'. Check if next char is '}'
            if end1 < len(content) and content[end1] == '}':
                # Extract inner: from after dimen{ to before }}
                # dimen starts at brace1_pos+len(dimen_part)
                dimen_part = m.group()
                inner_start = brace1_pos + len(dimen_part)
                inner = content[inner_start:end1 - 1] if end1 > inner_start else ''
                result.append(content[pos:abs_start])
                if inner:
                    result.append(inner)
                pos = end1 + 1  # skip past }}
                continue
            result.append(content[pos:end1])
            pos = end1
        result.append(content[pos:])
        return ''.join(result)

    @staticmethod
    def _wrap_leaked_math_blocks(content: str) -> str:
        """Wrap contiguous lines of leaked LaTeX math in $$...$$ blocks."""
        lines = content.split('\n')
        result = []
        in_code = False
        in_block_math = False

        math_cmds = ['\\mathbf', '\\boldsymbol', '\\mathrm', '\\mathcal',
                     '\\mathbb', '\\sum', '\\prod', '\\int', '\\frac',
                     '\\left', '\\right', '\\underbrace', '\\text',
                     '\\quad', '\\qquad', '\\alpha', '\\beta', '\\gamma',
                     '\\Gamma', '\\odot', '\\top', '\\in', '\\times',
                     '\\rightarrow', '\\mathrm']

        pending_math = []

        def _has_math_content(text):
            """Check if text contains actual LaTeX math (not prose with $)."""
            indicators = [
                r'\\mathbf', r'\\boldsymbol', r'\\mathrm', r'\\mathbb',
                r'\\sum', r'\\prod', r'\\int', r'\\frac', r'\\left', r'\
ight',
                r'\\underbrace', r'\\alpha', r'\\beta', r'\\gamma', r'\\theta',
                r'\\Gamma', r'\\Delta', r'\\odot', r'\\top', r'\\times', r'\\cdot',
                r'\
ightarrow', r'\\in', r'\\langle', r'\
angle',
                r'_\{\w', r'\^\{\w', r'_{\w', r'\^\w',
                r'\\hat', r'\\bar', r'\\tilde', r'\\begin\{', r'\\end\{',
                r'=\s*\\', r'&=\s*',
            ]
            return any(re.search(p, text) for p in indicators)

        def flush_math():
            if pending_math:
                combined = '\\n'.join(pending_math)
                if _has_math_content(combined):
                    result.append('$$')
                    result.extend(pending_math)
                    result.append('$$')
                else:
                    result.extend(pending_math)
                pending_math.clear()

        for line in lines:
            s = line.strip()

            if s.startswith('```'):
                flush_math()
                in_code = not in_code
                result.append(line)
                continue
            if in_code:
                flush_math()
                result.append(line)
                continue

            starts_dd = s.startswith('$$')
            ends_dd = s.endswith('$$')
            if starts_dd:
                flush_math()
                in_block_math = not (starts_dd and ends_dd and len(s) > 2)
                result.append(line)
                continue
            if ends_dd and not starts_dd:
                in_block_math = False
                result.append(line)
                continue
            if in_block_math or '$' in s or not s:
                flush_math()
                result.append(line)
                continue
            if s.startswith('#') or s.startswith('!['):
                flush_math()
                result.append(line)
                continue

            # Detect pure math lines: have math commands and almost no English words
            has_math = any(c in s for c in math_cmds)
            if has_math:
                stripped = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', s)
                stripped = re.sub(r'\{[^}]*\}', '', stripped)
                stripped = re.sub(r'[^a-zA-Z\s]', '', stripped).strip()
                words = [w for w in stripped.split() if len(w) > 2]
                if len(words) <= 3:
                    pending_math.append(line)
                    continue

            flush_math()
            result.append(line)

        flush_math()
        return '\n'.join(result)


# ─── Main Entry Point ────────────────────────────────────────────────

def _strip_comments_static(content: str) -> str:
    """Module-level comment stripper (used before resolve_input)."""
    lines = content.split('\n')
    result = []
    for line in lines:
        i = 0
        while i < len(line):
            if line[i] == '%' and (i == 0 or line[i-1] != '\\'):
                break
            i += 1
        result.append(line[:i])
    return '\n'.join(result)


def convert_tex_to_markdown(tex_dir: str, output_file: str,
                            title: str = None, author: str = None) -> str:
    """
    Convert a TeX source directory to a single Markdown file.

    Args:
        tex_dir: Path to the extracted TeX source directory
        output_file: Path for the output .md file
        title: Override title (if None, extracted from TeX)
        author: Override author (if None, extracted from TeX)

    Returns:
        Path to the output Markdown file
    """
    tex_dir = Path(tex_dir).absolute()
    output_file = Path(output_file).absolute()
    output_dir = output_file.parent
    images_dir = output_dir / "images"

    # Parse project
    project = TexProject(tex_dir)
    project.find_main_file()
    print(f"[tex2md] Main file: {project.main_file}")

    # Read main content
    content = project.main_file.read_text(encoding='utf-8', errors='replace')

    # Strip comments FIRST (before resolve_input, so commented-out \input is skipped)
    content = _strip_comments_static(content)

    # Resolve \input (now that comments are gone)
    content = project.resolve_input(content)
    print(f"[tex2md] Resolved \\input — merged content: {len(content)} chars")

    # Extract macros
    content = project.extract_macros(content)
    print(f"[tex2md] Extracted {len(project.custom_commands)} simple macros, "
          f"{len(project.macros)} parameterized macros")

    # Convert to Markdown
    converter = LatexToMarkdown(project, output_dir, images_dir)
    md_content = converter.convert(content)

    # Build title metadata
    if not title:
        title = project.title or project.main_file.stem
    if not author:
        author = project.authors or "Unknown"

    # Prepend title
    header = f"# {title}\n\n"
    if author and author != "Unknown":
        header += f"*{author}*\n\n---\n\n"
    md_content = header + md_content

    # Write output
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(md_content, encoding='utf-8')
    print(f"[tex2md] Output: {output_file}")
    print(f"[tex2md] Images dir: {images_dir}")

    # Count converted elements
    n_figures = len(list(images_dir.glob("*"))) if images_dir.exists() else 0
    print(f"[tex2md] Converted {n_figures} images, "
          f"{converter.figure_counter} figures, "
          f"{converter.table_counter} tables")

    return str(output_file)


def main():
    parser = argparse.ArgumentParser(description="Convert arXiv TeX source to Markdown")
    parser.add_argument('--tex-dir', required=True, help='Path to extracted TeX source directory')
    parser.add_argument('--output', '-o', required=True, help='Output .md file path')
    parser.add_argument('--title', default=None, help='Override title')
    parser.add_argument('--author', default=None, help='Override author')
    args = parser.parse_args()

    convert_tex_to_markdown(args.tex_dir, args.output, args.title, args.author)


if __name__ == '__main__':
    main()
