#!/usr/bin/env python3
"""Check Markdown file for $ / $$ delimiter pairing issues.

Scans a Markdown file for math delimiter problems that cause garbage MathML
and KFX conversion failures. See FP6b in fix_tokindle SKILL.md and
references/math-delimiter-debugging.md for the full case study.

Canonical copy (identical): D:/data/anan/projects/tokindle/scripts/check_math_delimiters.py
Also available at: tex_to_kindle skill scripts/check_math_delimiters.py

Usage:
    python check_math_delimiters.py <markdown_file>

Output: JSON to stdout with issue types:
    ODD_DD_COUNT   - odd number of $$ markers (unpaired block delimiter)
    ODD_D_COUNT    - odd number of $ markers (unpaired inline delimiter)
    STRAY_DD       - mid-line $$ with text before AND after (typo for $)
    MISPAIRED_DD   - $$ pair whose content contains headings/prose (not math)
    EMPTY_DD_PAIR  - $$ immediately followed by $$
"""

import re
import sys
import json
from pathlib import Path


def scan_delimiters(content: str) -> list:
    """Return list of all $ and $$ markers with position metadata."""
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
                markers.append({'type': '$$', 'pos': i, 'line': line_no, 'col': col, 'line_start': line_start})
                i += 2
            else:
                markers.append({'type': '$', 'pos': i, 'line': line_no, 'col': col, 'line_start': line_start})
                i += 1
        else:
            i += 1

    return markers


def get_line(content: str, pos: int) -> str:
    start = content.rfind('\n', 0, pos) + 1
    end = content.find('\n', pos)
    if end == -1:
        end = len(content)
    return content[start:end]


def get_context(content: str, pos: int, before: int = 50, after: int = 50) -> str:
    start = max(0, pos - before)
    end = min(len(content), pos + after)
    return content[start:end].replace('\n', '\\n')


def classify_dd_position(content: str, pos: int) -> str:
    """Classify $$ position: LINE_START, LINE_END, MID_LINE, or STANDALONE."""
    line = get_line(content, pos)
    col = pos - (content.rfind('\n', 0, pos) + 1)
    before = line[:col]
    after = line[col + 2:]
    if not before.rstrip() and not after.strip():
        return 'STANDALONE'
    elif not before.rstrip():
        return 'LINE_START'
    elif not after.strip():
        return 'LINE_END'
    else:
        return 'MID_LINE'


def check_issues(content: str) -> list:
    issues = []
    markers = scan_delimiters(content)
    dd_markers = [m for m in markers if m['type'] == '$$']
    sd_markers = [m for m in markers if m['type'] == '$']

    # Check 1: Odd $$ count
    if len(dd_markers) % 2 != 0:
        issues.append({
            'check': 'ODD_DD_COUNT', 'severity': 'CRITICAL',
            'message': f'Odd number of $$ markers ({len(dd_markers)}): '
                       f'one or more $$ is unpaired, causing all block formula '
                       f'pairing to be misaligned.',
            'dd_count': len(dd_markers),
        })

    # Check 2: Odd single-$ count
    if len(sd_markers) % 2 != 0:
        issues.append({
            'check': 'ODD_D_COUNT', 'severity': 'CRITICAL',
            'message': f'Odd number of single $ markers ({len(sd_markers)}): '
                       f'one or more inline formula $ is unpaired.',
            'd_count': len(sd_markers),
        })

    # Check 3: Stray $$ (mid-line with text before and after)
    for m in dd_markers:
        if classify_dd_position(content, m['pos']) == 'MID_LINE':
            issues.append({
                'check': 'STRAY_DD', 'severity': 'HIGH',
                'line': m['line'], 'col': m['col'],
                'message': f'Stray $$ on line {m["line"]}: has text both before '
                           f'and after. Likely a typo for $.',
                'context': get_context(content, m['pos']),
                'full_line': get_line(content, m['pos'])[:150],
                'suggestion': 'If this $$ ends an inline formula, change to $. '
                              'If it starts a block formula, move to its own line.',
            })

    # Check 4: Mis-paired $$ (content contains headings/prose)
    for i in range(0, len(dd_markers) - 1, 2):
        open_m, close_m = dd_markers[i], dd_markers[i + 1]
        inner = content[open_m['pos'] + 2:close_m['pos']]
        problems = []
        if re.search(r'^#{1,6}\s', inner, re.MULTILINE):
            problems.append('contains a Markdown heading')
        if re.search(r'^\s*[-*]\s', inner, re.MULTILINE):
            problems.append('contains Markdown list items')
        if '```' in inner:
            problems.append('contains code blocks')
        if re.search(r'!\[.*?\]\(.*?\)', inner):
            problems.append('contains image tags')
        if len(inner) > 500:
            problems.append(f'excessive length ({len(inner)} chars)')
        stripped = re.sub(r'\\[a-zA-Z]+\*?', '', inner)
        stripped = re.sub(r'\{[^}]*\}', '', stripped)
        stripped = re.sub(r'[^a-zA-Z\s]', '', stripped)
        english_words = re.findall(r'[a-zA-Z]{4,}', stripped)
        if len(english_words) > 15:
            problems.append(f'too many English words ({len(english_words)})')
        if problems:
            issues.append({
                'check': 'MISPAIRED_DD', 'severity': 'HIGH',
                'pair_index': i // 2,
                'open_line': open_m['line'], 'close_line': close_m['line'],
                'inner_length': len(inner), 'problems': problems,
                'message': f'$$ pair {i // 2 + 1} (lines {open_m["line"]}-'
                           f'{close_m["line"]}): {", ".join(problems)}.',
                'context_start': get_context(content, open_m['pos'], 20, 80),
                'context_end': get_context(content, close_m['pos'], 80, 20),
            })

    # Check 5: Empty $$ pairs
    for i in range(0, len(dd_markers) - 1, 2):
        open_m, close_m = dd_markers[i], dd_markers[i + 1]
        if not content[open_m['pos'] + 2:close_m['pos']].strip():
            issues.append({
                'check': 'EMPTY_DD_PAIR', 'severity': 'MEDIUM',
                'line': open_m['line'],
                'message': f'Empty $$ pair on line {open_m["line"]}.',
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
    markers = scan_delimiters(content)

    report = {
        'file': str(md_path), 'file_size': len(content),
        'total_dd_markers': sum(1 for m in markers if m['type'] == '$$'),
        'total_d_markers': sum(1 for m in markers if m['type'] == '$'),
        'issue_count': len(issues),
        'critical_count': sum(1 for i in issues if i['severity'] == 'CRITICAL'),
        'high_count': sum(1 for i in issues if i['severity'] == 'HIGH'),
        'issues': issues,
    }
    report['dd_paired'] = 'YES' if report['total_dd_markers'] % 2 == 0 else 'NO (ODD)'
    report['d_paired'] = 'YES' if report['total_d_markers'] % 2 == 0 else 'NO (ODD)'
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
