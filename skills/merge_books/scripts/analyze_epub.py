#!/usr/bin/env python3
"""Analyze EPUB structure: list all HTML files with lengths and preview text.

Essential first step before chapter extraction. Reveals:
- How many HTML files exist (chapter count, front/back matter)
- Each file's text length and opening lines (for alignment)
- Whether chapters are split across multiple files (common in Chinese EPUBs)
- Chapter numbering format (word numbers, digits, Chinese numerals, etc.)

Usage:
    python analyze_epub.py "path/to/book.epub"
    python analyze_epub.py --en en.epub --zh zh.epub   # side-by-side comparison
"""

import argparse
import re
import zipfile
from html.parser import HTMLParser


class HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip = True
        if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip = False
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.text.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data.strip())


def get_text(epub_path, hf):
    with zipfile.ZipFile(epub_path, "r") as z:
        content = z.read(hf).decode("utf-8", errors="ignore")
    p = HTMLToText()
    try:
        p.feed(content)
    except Exception:
        pass
    text = " ".join(p.text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def analyze_epub(epub_path, label=""):
    with zipfile.ZipFile(epub_path, "r") as z:
        names = z.namelist()
    html_files = sorted([n for n in names if n.endswith((".html", ".xhtml", ".htm"))])

    if label:
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")

    print(f"  Total HTML files: {len(html_files)}\n")

    for hf in html_files:
        text = get_text(epub_path, hf)
        if not text:
            print(f"  {hf:55s} len=      0  | (empty)")
            continue
        first = text[:150].replace("\n", " ")
        print(f"  {hf:55s} len={len(text):7d}  | {first}")

    return html_files


def main():
    parser = argparse.ArgumentParser(description="Analyze EPUB structure")
    parser.add_argument("epub", nargs="?", help="EPUB file to analyze")
    parser.add_argument("--en", help="English EPUB (for comparison)")
    parser.add_argument("--zh", help="Chinese EPUB (for comparison)")
    args = parser.parse_args()

    if args.en and args.zh:
        analyze_epub(args.en, "ENGLISH EPUB")
        analyze_epub(args.zh, "CHINESE EPUB")
        print(f"\n{'='*60}")
        print("Compare the file lists above to determine chapter alignment.")
        print("Look for: matching opening lines, chapter count differences,")
        print("front/back matter, and multi-file chapters (common in ZH EPUBs).")
        print(f"{'='*60}")
    elif args.epub:
        analyze_epub(args.epub)
    else:
        parser.error("Provide an EPUB path, or use --en and --zh for comparison")


if __name__ == "__main__":
    main()
