#!/usr/bin/env python3
"""table_renderer.py - Render TABLE_RAW LaTeX blocks as PNG images.

Reads a Markdown file, finds <!-- TABLE_RAW:N|caption -->...<!-- /TABLE_RAW:N -->
blocks, wraps each table in a standalone LaTeX document, compiles with pdflatex,
converts PDF → PNG, and replaces the blocks with Markdown image references.

Usage:
  python table_renderer.py paper.md --tex-dir /path/to/arxiv/src [--dpi 200]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Path to pdflatex
PDFLATEX = r"D:\storage\program\miktex\miktex\bin\x64\pdflatex.exe"

# Preamble for standalone table documents
TABLE_PREAMBLE = r"""
\documentclass[preview,border=8pt]{standalone}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{multicol}
\usepackage{colortbl}
\usepackage{xcolor}
\usepackage{array}
\usepackage{threeparttable}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{graphicx}
\usepackage{makecell}
\usepackage[font=small]{caption}
\usepackage[dvipsnames]{xcolor}

% Custom colors (from Kimi Linear and common palettes)
\definecolor{brickred}{HTML}{b92622}
\definecolor{midnightblue}{HTML}{005c7f}
\definecolor{limegreen}{HTML}{97c65a}
\definecolor{salmon}{HTML}{f1958d}
\definecolor{darkcyan}{HTML}{008B8B}
\definecolor{darkgrey}{rgb}{0.53,0.53,0.53}
\definecolor{mygrey}{rgb}{0.9,0.9,0.9}
\definecolor{kimiblue}{rgb}{0.09,0.5,0.99}

% Custom commands that may appear in tables
\newcommand{\white}[1]{\textcolor{white}{#1}}
\newcommand{\brickred}[1]{\textcolor{brickred}{#1}}
\newcommand{\midnightblue}[1]{\textcolor{midnightblue}{#1}}

\begin{document}
"""

TABLE_POSTAMBLE = r"\end{document}"


def find_pdflatex() -> str:
    """Locate pdflatex executable."""
    if os.path.isfile(PDFLATEX):
        return PDFLATEX
    # Try PATH
    for path in os.environ.get("PATH", "").split(os.pathsep):
        exe = os.path.join(path, "pdflatex.exe")
        if os.path.isfile(exe):
            return exe
    raise FileNotFoundError(
        "pdflatex not found. Install MiKTeX at D:\\storage\\program\\miktex\\"
    )


def compile_latex(tex_path: str, workdir: str) -> Path:
    """Compile a .tex file with pdflatex. Returns path to PDF."""
    pdflatex = find_pdflatex()
    for attempt in range(3):
        result = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", tex_path],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        pdf_path = Path(workdir) / Path(tex_path).with_suffix(".pdf").name
        if pdf_path.exists():
            return pdf_path
        if attempt == 2:
            # Show error on final attempt
            log_path = Path(workdir) / Path(tex_path).with_suffix(".log").name
            if log_path.exists():
                with open(log_path) as f:
                    log_content = f.read()
                # Extract error lines
                for line in log_content.split("\n"):
                    if line.startswith("!"):
                        print(f"  [table_renderer] LaTeX error: {line.strip()}")
            raise RuntimeError(f"pdflatex failed after 3 attempts")
    return None


def pdf_to_jpg(pdf_path: Path, output_dir: Path, dpi: int = 200) -> Path:
    """Convert PDF to JPEG using pymupdf."""
    import fitz  # pymupdf
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    jpg_name = pdf_path.stem + ".jpg"
    jpg_path = output_dir / jpg_name
    pix.save(str(jpg_path))
    doc.close()
    return jpg_path


def process_md(md_path: str, tex_dir: str, dpi: int = 200) -> str:
    """Process TABLE_RAW blocks in a Markdown file, replacing them with images."""
    md_path = Path(md_path).absolute()
    tex_dir = Path(tex_dir).absolute()
    images_dir = md_path.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find TABLE_RAW blocks: <!-- TABLE_RAW:N|caption -->...<!-- /TABLE_RAW:N -->
    pattern = re.compile(
        r'<!-- TABLE_RAW:(\d+)\|(.+?) -->[\r\n]+(.*?)[\r\n]+<!-- /TABLE_RAW:\1 -->',
        re.DOTALL,
    )
    matches = list(pattern.finditer(content))
    print(f"Found {len(matches)} TABLE_RAW block(s)")

    # Process in reverse order to preserve positions
    for match in reversed(matches):
        n = match.group(1)
        caption = match.group(2).strip()
        raw = match.group(3)

        # Restore escaped backslash-commands
        raw = raw.replace('\\LATEXBS', '\\')

        # Build document
        tex_content = TABLE_PREAMBLE + "\n" + raw + "\n" + TABLE_POSTAMBLE

        with tempfile.TemporaryDirectory() as tmpdir:
            tex_name = f"table_{n}.tex"
            tex_path = os.path.join(tmpdir, tex_name)
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(tex_content)

            print(f"  [table_{n}] Compiling...")
            pdf_path = compile_latex(tex_name, tmpdir)

            print(f"  [table_{n}] Converting PDF → JPEG...")
            jpg_path = pdf_to_jpg(pdf_path, images_dir, dpi)
            size = os.path.getsize(jpg_path)
            print(f"  [table_{n}] OK → images/{jpg_path.name} ({size:,} bytes)")

        # Replace with Markdown image
        replacement = (
            f'\n![{caption}](images/{jpg_path.name})\n\n'
            f'*{caption}*\n'
        )
        content = content[:match.start()] + replacement + content[match.end():]

    # Write updated content
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated: {md_path}")
    return str(md_path)


def main():
    parser = argparse.ArgumentParser(
        description="Render TABLE_RAW LaTeX blocks as PNG images in a Markdown file."
    )
    parser.add_argument("md_file", help="Path to the Markdown file to process")
    parser.add_argument("--tex-dir", help="TeX source directory (for reference, optional)")
    parser.add_argument("--dpi", type=int, default=200, help="DPI for PNG rendering (default: 200)")
    args = parser.parse_args()

    process_md(args.md_file, args.tex_dir or ".", args.dpi)


if __name__ == "__main__":
    main()
