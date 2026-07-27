#!/usr/bin/env python3
"""
Formula Region Extractor

Extracts all $...$ and $$...$$ regions from a Markdown file into a numbered
index for LLM review. The LLM can then identify problematic formulas and
the fixes can be applied back to the original MD.

Usage:
    python extract_formulas.py <paper.md> [--output formulas.txt]

Output format:
    [B1] Lines 74-78 (5 lines):
    $$\mathbf{S}_t = \mathbf{S}_{t-1} + \bm{k}_t \bm{v}_t^\top$$
    
    [I1] Line 50:
    $\mathrm{s.t.}, \square\in {\boldsymbol{q,k,v,o,u,w}}$

Summary at end:
    Block formulas: N, Inline formulas: M, Lines with issues: [...]
"""

import re
import sys
from pathlib import Path


def extract_formulas(md_path: str) -> dict:
    """Extract all formula regions from a Markdown file.
    
    Returns a dict with 'blocks' and 'inlines' lists, each containing
    {id, lines, content} entries.
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    blocks = []
    inlines = []
    
    # ── Extract $$...$$ blocks ──
    # Track multi-line blocks properly
    i = 0
    block_id = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith('$$'):
            # Check if single-line block
            if stripped.endswith('$$') and len(stripped) > 2:
                # Single-line: $$...$$
                inner = stripped[2:-2].strip()
                blocks.append({
                    'id': f'B{block_id + 1}',
                    'start_line': i + 1,
                    'end_line': i + 1,
                    'line_count': 1,
                    'content': f'$${inner}$$',
                })
                block_id += 1
            else:
                # Multi-line block opener
                start = i + 1
                # Build the block content
                block_lines = [lines[i]]
                i += 1
                while i < len(lines):
                    block_lines.append(lines[i])
                    if lines[i].strip().endswith('$$'):
                        break
                    i += 1
                end = i + 1
                inner = '\n'.join(block_lines)
                blocks.append({
                    'id': f'B{block_id + 1}',
                    'start_line': start,
                    'end_line': end,
                    'line_count': end - start + 1,
                    'content': inner,
                })
                block_id += 1
        i += 1
    
    # ── Extract $...$ inline formulas ──
    # Simple regex — finds $...$ pairs, skipping $$ that are part of blocks
    # We scan each line for $ that's NOT preceded or followed by another $
    inline_id = 0
    for line_no, line in enumerate(lines, 1):
        # Skip lines that are part of $$ blocks
        stripped = line.strip()
        if stripped.startswith('$$'):
            continue
        
        # Find inline $...$ pairs
        # Match: $ not preceded by $, then non-$ content, then $ not followed by $
        pattern = r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)'
        for m in re.finditer(pattern, line):
            inner = m.group(1)
            inlines.append({
                'id': f'I{inline_id + 1}',
                'line': line_no,
                'content': f'${inner}$',
            })
            inline_id += 1
    
    return {
        'blocks': blocks,
        'inlines': inlines,
        'total_lines': len(lines),
    }


def format_output(data: dict) -> str:
    """Format extracted formulas for LLM review."""
    out = []
    out.append(f"# Formula Region Index")
    out.append(f"File: {data.get('path', 'unknown')}")
    out.append(f"Total lines: {data['total_lines']}")
    out.append(f"Block formulas ($$...$$): {len(data['blocks'])}")
    out.append(f"Inline formulas ($...$): {len(data['inlines'])}")
    out.append("")
    
    if data['blocks']:
        out.append("## Block Formulas ($$...$$)")
        out.append("")
        for b in data['blocks']:
            if b['line_count'] == 1:
                out.append(f"[{b['id']}] Line {b['start_line']}:")
            else:
                out.append(f"[{b['id']}] Lines {b['start_line']}-{b['end_line']} "
                          f"({b['line_count']} lines):")
            out.append(b['content'])
            out.append("")
    
    if data['inlines']:
        out.append("## Inline Formulas ($...$)")
        out.append("")
        for f in data['inlines']:
            out.append(f"[{f['id']}] Line {f['line']}: {f['content']}")
        out.append("")
    
    # ── Issue detection hints ──
    out.append("## Auto-Detected Potential Issues")
    out.append("")
    
    issues = []
    for b in data['blocks']:
        inner = b['content']
        # Check for \operatorname, \bm{ (should be handled by tex2md.py v3.1)
        if '\\operatorname' in inner:
            issues.append(f"  [{b['id']}] contains \\operatorname → needs \\mathrm")
        if '\\bm{' in inner:
            issues.append(f"  [{b['id']}] contains \\bm{{ → needs \\boldsymbol{{")
        if '\\textcolor' in inner:
            issues.append(f"  [{b['id']}] contains \\textcolor → needs stripping")
        if '\\colorbox' in inner:
            issues.append(f"  [{b['id']}] contains \\colorbox → needs stripping")
        if '\\raisebox' in inner:
            issues.append(f"  [{b['id']}] contains \\raisebox → needs stripping")
        # Check brace balance
        if inner.count('{') != inner.count('}'):
            issues.append(f"  [{b['id']}] UNBALANCED BRACES: "
                         f"{{ count={inner.count('{')}, }} count={inner.count('}')}")
    
    for f in data['inlines']:
        inner = f['content']
        if inner.count('{') != inner.count('}'):
            issues.append(f"  [{f['id']}] UNBALANCED BRACES: "
                         f"{{ count={inner.count('{')}, }} count={inner.count('}')}")
    
    if issues:
        out.append("The following issues were auto-detected. The LLM should verify")
        out.append("and fix them in the original MD file.")
        out.append("")
        for issue in issues:
            out.append(issue)
        out.append("")
    else:
        out.append("No auto-detected issues. LLM should spot-check for:")
        out.append("- Overly complex formulas that might exceed latex2mathml limits")
        out.append("- Formulas that should be block ($$) but are inline ($)")
        out.append("- Formulas with ambiguous or malformed LaTeX syntax")
        out.append("")
    
    out.append("## LLM Review Instructions")
    out.append("")
    out.append("Read through ALL formulas above. For each issue you find, note:")
    out.append("1. The formula ID (e.g., B1, I3)")
    out.append("2. What's wrong")
    out.append("3. The corrected LaTeX")
    out.append("")
    out.append("Then use `patch` to fix the original MD file, or `execute_code`")
    out.append("for bulk replacements.")
    out.append("")
    
    return '\n'.join(out)


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_formulas.py <paper.md> [--output formulas.txt]")
        sys.exit(1)
    
    md_path = sys.argv[1]
    output_path = None
    
    # Parse --output flag
    args = sys.argv[1:]
    if '--output' in args:
        idx = args.index('--output')
        output_path = args[idx + 1]
    
    data = extract_formulas(md_path)
    data['path'] = md_path
    formatted = format_output(data)
    
    if output_path:
        Path(output_path).write_text(formatted, encoding='utf-8')
        print(f"Written to {output_path}")
    else:
        print(formatted)


if __name__ == '__main__':
    main()
