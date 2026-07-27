#!/usr/bin/env python3
"""code_renderer.py - Render CODE_RAW LaTeX code-listing blocks as PNG images.

Reads a Markdown file, finds <!-- CODE_RAW:N|caption -->...<!-- /CODE_RAW:N -->
blocks (minted/lstlisting/verbatim inside figure environments), wraps each in
a standalone LaTeX document, compiles with pdflatex (--shell-escape for minted),
converts PDF → PNG, and replaces the blocks with Markdown image references.

Usage:
  python code_renderer.py paper.md --dpi 150
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PDFLATEX = r"D:\storage\program\miktex\miktex\bin\x64\pdflatex.exe"

CODE_PREAMBLE = r"""
\documentclass[preview,border=8pt]{standalone}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{xcolor}
\usepackage[dvipsnames]{xcolor}
\usepackage{geometry}
\usepackage{fancyvrb}
\usepackage[most]{tcolorbox}
\usepackage{minted}
\usepackage{subcaption}
\usepackage{caption}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{bm}

% Common colors
\definecolor{brickred}{HTML}{b92622}
\definecolor{midnightblue}{HTML}{005c7f}
\definecolor{limegreen}{HTML}{97c65a}
\definecolor{salmon}{HTML}{f1958d}
\definecolor{darkcyan}{HTML}{008B8B}
\definecolor{darkgrey}{rgb}{0.53,0.53,0.53}
\definecolor{mygrey}{rgb}{0.9,0.9,0.9}
\definecolor{kimiblue}{rgb}{0.09,0.5,0.99}

% Common commands
\newcommand{\white}[1]{\textcolor{white}{#1}}
\newcommand{\brickred}[1]{\textcolor{brickred}{#1}}
\newcommand{\midnightblue}[1]{\textcolor{midnightblue}{#1}}

% Minted setup
\newenvironment{longlisting}{\captionsetup{type=listing,labelfont=bf}}{}
\setminted{
    fontsize=\footnotesize,
    fontfamily=tt,
    linenos,
    frame=lines,
    breaklines,
    numbersep=1.5pt,
}

\begin{document}
"""

CODE_POSTAMBLE = r"\end{document}"


def find_pdflatex() -> str:
    if os.path.isfile(PDFLATEX):
        return PDFLATEX
    for path in os.environ.get("PATH", "").split(os.pathsep):
        exe = os.path.join(path, "pdflatex.exe")
        if os.path.isfile(exe):
            return exe
    raise FileNotFoundError(
        "pdflatex not found. Install MiKTeX at D:\\storage\\program\\miktex\\"
    )


def compile_latex(tex_path: str, workdir: str) -> Path:
    pdflatex = find_pdflatex()
    for attempt in range(2):
        result = subprocess.run(
            [pdflatex, "-shell-escape", "-interaction=nonstopmode", tex_path],
            cwd=workdir, capture_output=True, text=True, timeout=120,
        )
        pdf_path = Path(workdir) / Path(tex_path).with_suffix(".pdf").name
        if pdf_path.exists():
            return pdf_path
        if attempt == 1:
            log_path = Path(workdir) / Path(tex_path).with_suffix(".log").name
            if log_path.exists():
                with open(log_path) as f:
                    for line in f:
                        if line.startswith("!"):
                            print(f"  [code_renderer] LaTeX error: {line.strip()}")
            raise RuntimeError("pdflatex failed after 2 attempts")
    return None


def pdf_to_jpg(pdf_path: Path, output_dir: Path, dpi: int = 150) -> Path:
    import fitz
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    jpg_name = pdf_path.stem + ".jpg"
    jpg_path = output_dir / jpg_name
    pix.save(str(jpg_path))
    doc.close()
    return jpg_path


def process_md(md_path: str, dpi: int = 150) -> str:
    md_path = Path(md_path).absolute()
    images_dir = md_path.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r'<!-- CODE_RAW:(\d+)\|(.*?) -->[\r\n]+(.*?)[\r\n]+<!-- /CODE_RAW:\1 -->',
        re.DOTALL,
    )
    matches = list(pattern.finditer(content))
    print(f"Found {len(matches)} CODE_RAW block(s)")

    for match in reversed(matches):
        n = match.group(1)
        caption = match.group(2).strip()
        raw = match.group(3)

        # Restore escaped backslash-commands
        raw = raw.replace("\\LATEXBS", "\\")
        # Wrap in figure environment for proper caption/label rendering
        raw = f"\\begin{{figure}}\n{raw}\n\\end{{figure}}"

        tex_content = CODE_PREAMBLE + "\n" + raw + "\n" + CODE_POSTAMBLE

        with tempfile.TemporaryDirectory() as tmpdir:
            tex_name = f"code_{n}.tex"
            tex_path = os.path.join(tmpdir, tex_name)
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(tex_content)

            print(f"  [code_{n}] Compiling (with minted)...")
            pdf_path = compile_latex(tex_name, tmpdir)

            print(f"  [code_{n}] Converting PDF → JPEG...")
            jpg_path = pdf_to_jpg(pdf_path, images_dir, dpi)
            size = os.path.getsize(jpg_path)
            print(f"  [code_{n}] OK → images/{jpg_path.name} ({size:,} bytes)")

        replacement = (
            f'\n![{caption}](images/{jpg_path.name})\n\n'
            f'*{caption}*\n'
        )
        content = content[:match.start()] + replacement + content[match.end():]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated: {md_path}")
    return str(md_path)


def main():
    parser = argparse.ArgumentParser(
        description="Render CODE_RAW LaTeX code-listing blocks as PNG images."
    )
    parser.add_argument("md_file", help="Path to the Markdown file to process")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for PNG rendering (default: 150)")
    args = parser.parse_args()
    process_md(args.md_file, args.dpi)


if __name__ == "__main__":
    main()
