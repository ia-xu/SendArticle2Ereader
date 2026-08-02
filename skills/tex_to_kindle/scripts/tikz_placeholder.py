"""
TikZ Placeholder Resolver — MiKTeX Integration

Scans a Markdown file for <!-- TIKZ_FIGURE:path --> placeholders,
compiles each .tex figure with MiKTeX (pdflatex), converts PDF to PNG,
and replaces the placeholder with a proper Markdown image reference.

Also handles <!-- MISSING_IMAGE:path --> for \includegraphics that
couldn't be resolved — tries harder to find the file, or leaves a note.

Usage:
    python tikz_placeholder.py <markdown_file> --tex-dir <tex_source_dir> [--dpi 200]

Output:
    Modifies the .md file in place. Produces images/ next to the .md file.
"""

import os
import re
import sys
import argparse
import subprocess
import shutil
import tempfile
from pathlib import Path

PDFLATEX = r"D:\storage\program\miktex\miktex\bin\x64\pdflatex.exe"

# LaTeX preamble for standalone TikZ compilation.
# Uses {input_path} placeholder (NOT %s) to avoid Python %-formatting conflicts
# with LaTeX % comments.
TIKZ_PREAMBLE = r"""\documentclass[border=5pt]{standalone}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsfonts,bm,mathrsfs,mathtools}
\usepackage[dvipsnames]{xcolor}

\definecolor{brickred}{HTML}{b92622}
\definecolor{midnightblue}{HTML}{005c7f}
\definecolor{limegreen}{HTML}{97c65a}
\definecolor{salmon}{HTML}{f1958d}
\definecolor{darkcyan}{HTML}{008B8B}
\definecolor{darkgrey}{rgb}{0.53,0.53,0.53}
\definecolor{mygrey}{rgb}{0.9,0.9,0.9}
\definecolor{kimiblue}{rgb}{0.09,0.5,0.99}

\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usetikzlibrary{
  arrows.meta, positioning, calc,
  shapes.geometric, shapes.misc, shapes.symbols,
  decorations.text, decorations.pathreplacing, decorations.pathmorphing,
  decorations.shapes, calligraphy,
  patterns, patterns.meta,
  fit, backgrounds, chains, shadows,
  math, matrix, circuits.ee.IEC,
  plotmarks
}

\usepackage{adjustbox}
\usepackage{subcaption}
\usepackage{wrapfig}
\usepackage{makecell}
\usepackage{booktabs}
\usepackage{colortbl}
\usepackage{multirow}

\begin{document}
\input{__TEX_PATH__}
\end{document}
"""


def scan_placeholders(md_content: str) -> list:
    """Find all <!-- TIKZ_FIGURE:path --> placeholders."""
    pattern = r'<!--\s*TIKZ_FIGURE:([^\s>]+)\s*-->'
    matches = []
    for m in re.finditer(pattern, md_content):
        matches.append({
            'full': m.group(0),
            'path': m.group(1).strip(),
            'start': m.start(),
            'end': m.end(),
        })
    return matches


def _extract_figure_body(content: str) -> str:
    """Strip figure/wrapfigure/subfigure wrappers, keep inner content.

    Handles: \\begin{figure}..\\end{figure}, \\begin{figure*}..\\end{figure*},
    \\begin{wrapfigure}..\\end{wrapfigure}, \\begin{subfigure}..\\end{subfigure},
    \\begin{adjustbox}..\\end{adjustbox}.
    Removes: \\caption{...}, \\label{...}, \\captionsetup{...}, \\centering.
    Uses balanced-brace matching for \\caption{...} to handle \\subref and
    other nested-brace commands correctly.
    """
    # Remove env wrappers (line-level — just strip the \\begin and \\end lines)
    body = re.sub(r'\\begin\{(?:wrap)?figure\*?\}.*?\n', '', content, flags=re.DOTALL)
    body = re.sub(r'\\end\{(?:wrap)?figure\*?\}', '', body)
    body = re.sub(r'\\begin\{subfigure\}.*?\n', '', body, flags=re.DOTALL)
    body = re.sub(r'\\end\{subfigure\}', '', body)
    body = re.sub(r'\\begin\{adjustbox\}.*?\n', '', body, flags=re.DOTALL)
    body = re.sub(r'\\end\{adjustbox\}', '', body)

    # Remove \\caption{...} with balanced brace matching
    body = _remove_balanced_command(body, r'\\caption')

    # Remove \\label{...}, \\captionsetup{...}
    body = re.sub(r'\\label\{[^}]*\}', '', body)
    body = _remove_balanced_command(body, r'\\captionsetup')

    # Remove layout commands
    body = re.sub(r'\\centering\s*', '', body)
    body = re.sub(r'\\vspace\{[^}]*\}', '', body)
    body = re.sub(r'\\hspace\{[^}]*\}', '', body)

    return body.strip()


def _remove_balanced_command(text: str, cmd_pattern: str) -> str:
    """Remove \\cmd{...} from text, using balanced brace matching.
    
    Handles nested braces like \\caption{\\subref{fig:x} text}.
    cmd_pattern should be the raw regex for the command, e.g. r'\\\\caption'.
    """
    result = []
    pos = 0
    while True:
        m = re.search(cmd_pattern + r'\s*\{', text[pos:])
        if not m:
            break
        abs_start = pos + m.start()
        brace_start = pos + m.end() - 1  # position of '{'
        length, end = _balanced_braces(text, brace_start)
        result.append(text[pos:abs_start])
        pos = end
    result.append(text[pos:])
    return ''.join(result)


def _balanced_braces(s: str, start: int) -> tuple:
    """Find matching '}' for '{' at 'start'. Returns (length, end_pos)."""
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


def _compile_body(figure_body: str, output_jpg: Path, dpi: int = 200,
                  label: str = "figure") -> bool:
    """Compile a raw LaTeX body (tikzpicture) to PNG using MiKTeX + pymupdf."""
    if not Path(PDFLATEX).exists():
        print(f"  [ERROR] pdflatex not found at {PDFLATEX}")
        return False

    workdir = tempfile.mkdtemp(prefix='tikz_ph_')

    try:
        # Build standalone document with body inlined (no input)
        wrapper_tex = os.path.join(workdir, 'figure.tex')
        doc = TIKZ_PREAMBLE.replace('\input{__TEX_PATH__}', figure_body)
        with open(wrapper_tex, 'w', encoding='utf-8') as f:
            f.write(doc)

        # Run pdflatex (twice for cross-refs)
        for _ in range(2):
            subprocess.run(
                [PDFLATEX, "-interaction=nonstopmode", "figure.tex"],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=120
            )

        pdf_path = os.path.join(workdir, 'figure.pdf')
        if not os.path.exists(pdf_path):
            # Check log for errors
            log_path = os.path.join(workdir, 'figure.log')
            if os.path.exists(log_path):
                with open(log_path, 'r') as f:
                    log = f.read()
                errors = [l.strip() for l in log.split('\n') if l.startswith('!')]
                if errors:
                    print(f"  [WARNING] LaTeX errors for {label}:")
                    for e in errors[:3]:
                        print(f"    {e}")
            return False

        # Convert PDF -> PNG
        import fitz
        doc = fitz.open(pdf_path)
        page = doc[0]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        pix.save(str(output_jpg))
        doc.close()
        return True

    except Exception as e:
        print(f"  [ERROR] {label}: {e}")
        return False
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def compile_tikz(tex_path: Path, output_jpg: Path, dpi: int = 200) -> bool:
    """Compile a .tex TikZ figure to PNG using MiKTeX pdflatex + pymupdf."""
    tex_path = Path(tex_path)
    try:
        raw = tex_path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        print(f"  [ERROR] Cannot read {tex_path.name}: {e}")
        return False
    figure_body = _extract_figure_body(raw)
    return _compile_body(figure_body, output_jpg, dpi=dpi, label=tex_path.name)
def resolve_placeholders(md_path: str, tex_dir: str, dpi: int = 200) -> int:
    """Main entry point: resolve all TIKZ_FIGURE placeholders in a .md file.

    Returns number of placeholders resolved.
    """
    md_path = Path(md_path)
    tex_dir = Path(tex_dir)
    images_dir = md_path.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    content = md_path.read_text(encoding='utf-8')

    # === Phase 1: TIKZ_FIGURE placeholders ===
    placeholders = scan_placeholders(content)
    if not placeholders:
        print("No TIKZ_FIGURE placeholders found.")
        return 0

    print(f"Found {len(placeholders)} TIKZ_FIGURE placeholder(s)")

    resolved = 0
    # Process in reverse order so indices stay valid
    for ph in reversed(placeholders):
        tex_rel = ph['path']
        tex_abs = tex_dir / tex_rel

        if not tex_abs.exists():
            print(f"  [SKIP] {tex_rel} — file not found at {tex_abs}")
            continue

        name = tex_abs.stem
        jpg_name = f"{name}.jpg"
        jpg_path = images_dir / jpg_name

        print(f"  [{name}] Compiling...")
        if compile_tikz(tex_abs, jpg_path, dpi=dpi):
            size = jpg_path.stat().st_size if jpg_path.exists() else 0
            print(f"  [{name}] OK → images/{jpg_name} ({size:,} bytes)")

            # Replace placeholder with image reference
            replacement = f"![{name}](images/{jpg_name})"
            content = content[:ph['start']] + replacement + content[ph['end']:]
            resolved += 1
        else:
            print(f"  [{name}] FAILED — leaving placeholder in place")
            # Replace with a visible note
            replacement = f"> *[Figure: {name} — TikZ compilation failed]*"
            content = content[:ph['start']] + replacement + content[ph['end']:]

    # === Phase 2: MISSING_IMAGE placeholders ===
    missing_pattern = r'<!--\s*MISSING_IMAGE:([^\s>]+)\s*-->'
    missing_matches = list(re.finditer(missing_pattern, content))
    if missing_matches:
        print(f"\nFound {len(missing_matches)} MISSING_IMAGE placeholder(s)")
        for m in reversed(missing_matches):
            img_path = m.group(1).strip()
            img_name = Path(img_path).name
            # Try to find in tex_dir or figures/
            for search_dir in [tex_dir, tex_dir / 'figures']:
                for ext in ['.pdf', '.png', '.jpg', '.jpeg']:
                    p = search_dir / (Path(img_path).stem + ext)
                    if p.exists():
                        if p.suffix.lower() == '.pdf':
                            import fitz
                            doc = fitz.open(str(p))
                            pix = doc[0].get_pixmap(
                                matrix=fitz.Matrix(dpi/72, dpi/72))
                            jpg_path = images_dir / f"{p.stem}.jpg"
                            pix.save(str(jpg_path))
                            doc.close()
                        else:
                            jpg_path = images_dir / p.name
                            shutil.copy2(p, jpg_path)
                        replacement = f"![{p.stem}](images/{jpg_path.name})"
                        content = content[:m.start()] + replacement + content[m.end():]
                        print(f"  [RESOLVED] {img_path} → images/{jpg_path.name}")
                        break
                else:
                    continue
                break
            else:
                # Still not found — leave a note
                replacement = f"> *[Figure: {img_name} — image not found]*"
                content = content[:m.start()] + replacement + content[m.end():]

    # === Phase 3: TIKZ_RAW blocks (inline tikzpicture inside figure env) ===
    tikz_raw_pattern = re.compile(
        r'<!--\s*TIKZ_RAW:(\d+)\|(.*?) -->[\r\n]+(.*?)[\r\n]+<!-- /TIKZ_RAW:\1 -->',
        re.DOTALL
    )
    raw_matches = list(tikz_raw_pattern.finditer(content))
    resolved_raw = 0
    if raw_matches:
        print(f"\nFound {len(raw_matches)} TIKZ_RAW block(s)")
        for m in reversed(raw_matches):
            n = m.group(1)
            caption = m.group(2)
            raw = m.group(3).replace('\\LATEXBS', '\\')
            body = _extract_figure_body(raw)
            jpg_name = f"tikz_{n}.png"
            jpg_path = images_dir / jpg_name
            print(f"  [tikz_raw:{n}] Compiling inline tikzpicture...")
            if _compile_body(body, jpg_path, dpi=dpi, label=f"tikz_raw:{n}"):
                size = jpg_path.stat().st_size if jpg_path.exists() else 0
                print(f"  [tikz_raw:{n}] OK -> images/{jpg_name} ({size:,} bytes)")
                alt = re.sub(r'[\[\]]', '', caption) or f"Figure {n}"
                replacement = f"![{alt}](images/{jpg_name})"
                content = content[:m.start()] + replacement + content[m.end():]
                resolved_raw += 1
            else:
                print(f"  [tikz_raw:{n}] FAILED - leaving a visible note")
                alt = re.sub(r'[\[\]]', '', caption) or n
                replacement = f"> *[Figure: {alt} - TikZ compilation failed]*"
                content = content[:m.start()] + replacement + content[m.end():]

    # Write back
    md_path.write_text(content, encoding='utf-8')
    print(f"\nDone: {resolved}/{len(placeholders)} TikZ figures resolved, "
          f"{resolved_raw}/{len(raw_matches)} TIKZ_RAW blocks resolved")
    print(f"Updated: {md_path}")

    return resolved


def main():
    parser = argparse.ArgumentParser(
        description="Resolve TikZ placeholders in a Markdown file using MiKTeX")
    parser.add_argument('md_file', help='Path to the Markdown file')
    parser.add_argument('--tex-dir', required=True,
                        help='Path to the original TeX source directory')
    parser.add_argument('--dpi', type=int, default=200,
                        help='Output PNG DPI (default: 200)')
    args = parser.parse_args()

    resolve_placeholders(args.md_file, args.tex_dir, args.dpi)


if __name__ == '__main__':
    main()
