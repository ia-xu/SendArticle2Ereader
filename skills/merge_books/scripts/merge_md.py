#!/usr/bin/env python3
"""Merge individual chapter Markdown files into a single book.

Usage:
    python merge_md.py --dir book_dir/markdown --title "天生就会跑 (中英对照)" --output merged_book.md
"""

import argparse
import os
import glob
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="Merge chapter MDs into one book")
    parser.add_argument("--dir", required=True, help="markdown directory")
    parser.add_argument("--title", default="Bilingual Book", help="Book title")
    parser.add_argument("--author", default="", help="Author name")
    parser.add_argument("--output", default="merged_book.md", help="Output filename")
    args = parser.parse_args()

    md_dir = args.dir

    chapter_files = sorted(glob.glob(os.path.join(md_dir, "ch*.md")))
    if not chapter_files:
        print(f"No chapter files found in {md_dir}")
        return

    print(f"Found {len(chapter_files)} chapter files")

    parts = []
    parts.append(f"# {args.title}\n")
    if args.author:
        parts.append(f"**{args.author}**\n")
    parts.append("\n> English-Chinese Bilingual Edition | 中英对照版\n")
    parts.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d')}\n")
    parts.append("\n---\n")

    for cf in chapter_files:
        with open(cf, "r", encoding="utf-8") as f:
            content = f.read().strip()
        parts.append(content)
        parts.append("\n\n---\n")

    output_path = os.path.join(md_dir, args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(f"Merged book written to: {output_path}")
    print(f"Total size: {os.path.getsize(output_path)} bytes")


if __name__ == "__main__":
    main()
