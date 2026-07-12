#!/usr/bin/env python3
"""Extract chapters from English and Chinese EPUB files into text files.

Usage:
    python extract_chapters.py --en english.epub --zh chinese.epub --out book_dir [--chapters 25-32]
"""

import argparse
import json
import os
import re
import zipfile
from html.parser import HTMLParser


class HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.tag_stack = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        self.tag_stack.append(tag)
        if tag in ("style", "script"):
            self.skip = True
        if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()
        if tag in ("style", "script"):
            self.skip = False
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.text.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data.strip())


def epub_to_chapters(epub_path):
    """Extract all chapters from an EPUB file."""
    with zipfile.ZipFile(epub_path, "r") as z:
        names = z.namelist()
        html_files = [n for n in names if n.endswith((".html", ".xhtml", ".htm"))]
        chapters = []
        for hf in sorted(html_files):
            content = z.read(hf).decode("utf-8", errors="ignore")
            parser = HTMLToText()
            try:
                parser.feed(content)
            except Exception:
                pass
            text = " ".join(parser.text).strip()
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r"[ \t]+", " ", text)
            if len(text) > 100:
                chapters.append({"file": hf, "text": text, "length": len(text)})
        return chapters


def detect_chapter_offset(chapters, lang="en"):
    """Find where chapter 1 starts (0-indexed offset)."""
    for i, ch in enumerate(chapters):
        text = ch["text"][:200]
        if lang == "en":
            if re.search(r"CHAPTER\s*1\b", text, re.IGNORECASE):
                return i - 1  # chapter 1 is at this index, so offset is i-1
        else:
            cn_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
            if "第一章" in text or "第1章" in text:
                return i - 1
    return 1  # default: first real chapter at index 2, offset=1


def main():
    parser = argparse.ArgumentParser(description="Extract chapters from EPUBs")
    parser.add_argument("--en", required=True, help="English EPUB path")
    parser.add_argument("--zh", required=True, help="Chinese EPUB path")
    parser.add_argument("--out", required=True, help="Output book directory")
    parser.add_argument("--chapters", default=None, help="Chapter range, e.g. 25-32")
    args = parser.parse_args()

    en_chapters = epub_to_chapters(args.en)
    zh_chapters = epub_to_chapters(args.zh)

    en_offset = detect_chapter_offset(en_chapters, "en")
    zh_offset = detect_chapter_offset(zh_chapters, "zh")

    # Determine chapter range
    if args.chapters:
        start, end = map(int, args.chapters.split("-"))
        chapter_nums = list(range(start, end + 1))
    else:
        # Detect max chapters
        max_en = len(en_chapters) - en_offset - 1
        max_zh = len(zh_chapters) - zh_offset - 1
        max_ch = min(max_en, max_zh)
        chapter_nums = list(range(1, max_ch + 1))

    os.makedirs(f"{args.out}/chapters/en", exist_ok=True)
    os.makedirs(f"{args.out}/chapters/zh", exist_ok=True)
    os.makedirs(f"{args.out}/markdown", exist_ok=True)

    chapter_map = {}
    for ch_num in chapter_nums:
        en_idx = ch_num + en_offset
        zh_idx = ch_num + zh_offset

        if en_idx >= len(en_chapters) or zh_idx >= len(zh_chapters):
            print(f"Ch{ch_num}: SKIP (index out of range)")
            continue

        en_text = en_chapters[en_idx]["text"]
        zh_text = zh_chapters[zh_idx]["text"]

        # Clean repeated headers
        en_text = re.sub(r"^Born to Run:.*?(?=CHAPTER)", "", en_text, flags=re.DOTALL).strip()
        zh_text = re.sub(r"^天生就会跑\s*", "", zh_text).strip()

        en_file = f"{args.out}/chapters/en/ch{ch_num:02d}.txt"
        zh_file = f"{args.out}/chapters/zh/ch{ch_num:02d}.txt"

        with open(en_file, "w", encoding="utf-8") as f:
            f.write(en_text)
        with open(zh_file, "w", encoding="utf-8") as f:
            f.write(zh_text)

        chapter_map[ch_num] = {
            "en_file": en_file,
            "zh_file": zh_file,
            "en_len": len(en_text),
            "zh_len": len(zh_text),
        }
        print(f"Ch{ch_num}: EN={len(en_text)} chars, ZH={len(zh_text)} chars")

    with open(f"{args.out}/chapter_map.json", "w", encoding="utf-8") as f:
        json.dump(chapter_map, f, ensure_ascii=False, indent=2)

    print(f"\nExtracted {len(chapter_map)} chapters to {args.out}/chapters/")
    print("Verify alignment before merging!")


if __name__ == "__main__":
    main()
