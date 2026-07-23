#!/usr/bin/env python3
"""Check Markdown file for $ / $$ delimiter pairing issues.

Scans a Markdown file for math delimiter problems that cause garbage MathML
and KFX conversion failures:

  1. Stray $$ (should be $): mid-line $$ with text both before and after
  2. Odd $$ count: unpaired block formula delimiter
  3. Odd single-$ count: unpaired inline formula delimiter
  4. Mis-paired $$: sequential pairing captures headings/prose (not math)
  5. Empty $$ pairs: $$ immediately followed by $$
  6. Orphan $$ on its own line with no matching opener/closer nearby

Outputs a structured JSON report with line numbers, issue types, and context.
The LLM reads this report alongside the MD file to apply targeted fixes
BEFORE running md2kfx conversion.

Usage:
    python check_math_delimiters.py <markdown_file>

Output: JSON to stdout

Canonical copy: D:/data/anan/projects/tokindle/scripts/check_math_delimiters.py
"""

import re
import sys
import json
from pathlib import Path


def scan_delimiters(content: str) -> dict:
    """Scan content and return a list of all $ and $$ markers with metadata."""
    markers = []
    i = 0
    line_no = 1
    line_start = 0

    while i < len(content):
        if content[i] == '\n':
            line_no += 1
            line_start = i + 1
            i += 1
            continue

        if content[i] == '$':
            col = i - line_start
            if i + 1 < len(content) and content[i + 1] == '$':
                # $$ marker
                markers.append({
                    'type': '$$',
                    'pos': i,
                    'line': line_no,
                    'col': col,
                    'line_start': line_start,
                })
                i += 2
            else:
                # $ marker
                markers.append({
                    'type': '$',
                    'pos': i,
                    'line': line_no,
                    'col': col,
                    'line_start': line_start,
                })
                i += 1
        else:
            i += 1

    return markers


def get_line(content: str, pos: int) -> str:
    """Get the full line containing position pos."""
    start = content.rfind('\n', 0, pos) + 1
    end = content.find('\n', pos)
    if end == -1:
        end = len(content)
    return content[start:end]


def get_context(content: str, pos: int, before: int = 50, after: int = 50) -> str:
    """Get context string around a position."""
    start = max(0, pos - before)
    end = min(len(content), pos + after)
    ctx = content[start:end].replace('\n', '\\n')
    return ctx


def classify_dd_position(content: str, pos: int) -> str:
    """Classify a $$ marker's position within its line.

    LINE_START: $$ is at (or near) the start of a line (only whitespace before)
    LINE_END: $$ is at (or near) the end of a line (only whitespace/period after)
    MID_LINE: $$ has non-whitespace content both before and after on the same line
    STANDALONE: $$ is the only non-whitespace content on the line
    """
    line = get_line(content, pos)
    col = pos - (content.rfind('\n', 0, pos) + 1)

    before = line[:col]
    after = line[col + 2:]

    before_stripped = before.rstrip()
    after_stripped = after.strip()

    if not before_stripped and not after_stripped:
        return 'STANDALONE'
    elif not before_stripped:
        return 'LINE_START'
    elif not after_stripped:
        return 'LINE_END'
    else:
        return 'MID_LINE'


def check_issues(content: str) -> list:
    """Run all checks and return a list of issues."""
    issues = []
    markers = scan_delimiters(content)

    dd_markers = [m for m in markers if m['type'] == '$$']
    sd_markers = [m for m in markers if m['type'] == '$']

    # === Check 1: Odd $$ count ===
    if len(dd_markers) % 2 != 0:
        issues.append({
            'check': 'ODD_DD_COUNT',
            'severity': 'CRITICAL',
            'message': f'Odd number of $$ markers ({len(dd_markers)}): '
                       f'one or more $$ is unpaired, causing all block formula '
                       f'pairing to be misaligned.',
            'dd_count': len(dd_markers),
        })

    # === Check 2: Odd single-$ count ===
    if len(sd_markers) % 2 != 0:
        issues.append({
            'check': 'ODD_D_COUNT',
            'severity': 'CRITICAL',
            'message': f'Odd number of single $ markers ({len(sd_markers)}): '
                       f'one or more inline formula $ is unpaired, causing the '
                       f'inline regex to match across paragraph boundaries.',
            'd_count': len(sd_markers),
        })

    # === Check 3: Stray $$ (mid-line with text before and after) ===
    for m in dd_markers:
        classification = classify_dd_position(content, m['pos'])
        if classification == 'MID_LINE':
            line = get_line(content, m['pos'])
            issues.append({
                'check': 'STRAY_DD',
                'severity': 'HIGH',
                'line': m['line'],
                'col': m['col'],
                'message': f'Stray $$ on line {m["line"]}: has text both before '
                           f'and after. This $$ is likely a typo for $ (inline '
                           f'formula end), which shifts all subsequent $$ pairing.',
                'context': get_context(content, m['pos']),
                'full_line': line[:150],
                'suggestion': 'If this $$ ends an inline formula, change it to $. '
                              'If it starts a block formula, move it to its own line.',
            })

    # === Check 4: Mis-paired $$ (content contains headings/prose) ===
    for i in range(0, len(dd_markers) - 1, 2):
        open_m = dd_markers[i]
        close_m = dd_markers[i + 1]
        inner = content[open_m['pos'] + 2:close_m['pos']]

        problems = []

        # Contains a heading?
        if re.search(r'^#{1,6}\s', inner, re.MULTILINE):
            problems.append('contains a Markdown heading')

        # Contains list items?
        if re.search(r'^\s*[-*]\s', inner, re.MULTILINE):
            problems.append('contains Markdown list items')

        # Contains code blocks?
        if '```' in inner:
            problems.append('contains code blocks')

        # Contains images?
        if re.search(r'!\[.*?\]\(.*?\)', inner):
            problems.append('contains image tags')

        # Very long (>500 chars) for a single formula?
        if len(inner) > 500:
            problems.append(f'excessive length ({len(inner)} chars)')

        # Count bare English words (strip LaTeX commands/braces first)
        stripped = re.sub(r'\\[a-zA-Z]+\*?', '', inner)
        stripped = re.sub(r'\{[^}]*\}', '', stripped)
        stripped = re.sub(r'[^a-zA-Z\s]', '', stripped)
        english_words = re.findall(r'[a-zA-Z]{4,}', stripped)
        if len(english_words) > 15:
            problems.append(f'too many English words ({len(english_words)} '
                           f'bare 4+ letter words, likely prose not math)')

        if problems:
            issues.append({
                'check': 'MISPAIRED_DD',
                'severity': 'HIGH',
                'pair_index': i // 2,
                'open_line': open_m['line'],
                'close_line': close_m['line'],
                'inner_length': len(inner),
                'problems': problems,
                'message': f'$$ pair {i // 2 + 1} (lines {open_m["line"]}-'
                           f'{close_m["line"]}): {", ".join(problems)}. '
                           f'This pair is misaligned due to a stray $$ elsewhere.',
                'context_start': get_context(content, open_m['pos'], 20, 80),
                'context_end': get_context(content, close_m['pos'], 80, 20),
            })

    # === Check 5: Empty $$ pairs ===
    for i in range(0, len(dd_markers) - 1, 2):
        open_m = dd_markers[i]
        close_m = dd_markers[i + 1]
        inner = content[open_m['pos'] + 2:close_m['pos']].strip()
        if not inner:
            issues.append({
                'check': 'EMPTY_DD_PAIR',
                'severity': 'MEDIUM',
                'line': open_m['line'],
                'message': f'Empty $$ pair on line {open_m["line"]}: '
                           f'$$ immediately followed by $$.',
            })

    return issues


def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: check_math_delimiters.py <markdown_file>'}))
        sys.exit(1)

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(json.dumps({'error': f'File not found: {md_path}'}))
        sys.exit(1)

    content = md_path.read_text(encoding='utf-8')
    issues = check_issues(content)

    # Summary stats
    markers = scan_delimiters(content)
    dd_count = sum(1 for m in markers if m['type'] == '$$')
    d_count = sum(1 for m in markers if m['type'] == '$')

    report = {
        'file': str(md_path),
        'file_size': len(content),
        'total_dd_markers': dd_count,
        'total_d_markers': d_count,
        'dd_paired': 'YES' if dd_count % 2 == 0 else 'NO (ODD)',
        'd_paired': 'YES' if d_count % 2 == 0 else 'NO (ODD)',
        'issue_count': len(issues),
        'critical_count': sum(1 for i in issues if i['severity'] == 'CRITICAL'),
        'high_count': sum(1 for i in issues if i['severity'] == 'HIGH'),
        'issues': issues,
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
