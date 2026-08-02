"""Build equation label->number map from a LaTeX project in document order.

Usage:
  python build_eq_map.py --tex-dir <source_dir> [--main main.tex] [--out map.txt]

Why: tex2md's \\eqref handling drops the FIRST character of the label
(P44): \\eqref{eq:latentmoe} -> "(Equation atentmoe)". To fix refs in the MD,
compute the real equation numbers by walking the project in \\input order.

Numbering rules (standard amsmath):
  equation/gather/multline : +1 per env (label inside captures current number)
  align/eqnarray           : +1 per row (rows split on \\\\, skip \\nonumber/\\notag)
  \\[ \\] and *-forms      : unnumbered
"""
import argparse
import re
from pathlib import Path

EQ_RE = re.compile(r'\\begin\{(equation|align|gather|multline|eqnarray)\*?\}')
END_RE = re.compile(r'\\end\{(equation|align|gather|multline|eqnarray)\*?\}')
LABEL_RE = re.compile(r'\\label\{([^}]+)\}')
NONUMBER_RE = re.compile(r'\\nonumber|\\notag')


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def resolve_inputs(main: Path, tex_dir: Path):
    """Ordered (filename, content) pairs following \\input/\\include resolution."""
    files = []
    seen = set()

    def walk(text, path):
        text = re.sub(r'(?<!\\)%.*', '', text)
        for m in re.finditer(r'\\(?:input|include)\{([^}]+)\}', text):
            name = m.group(1)
            for cand in (name + ".tex", name):
                p = (tex_dir / cand).resolve()
                if p.is_file() and str(p) not in seen:
                    seen.add(str(p))
                    files.append((p, read(p)))
                    walk(files[-1][1], p)
                    break

    walk(read(main), main)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex-dir", required=True)
    ap.add_argument("--main", default="main.tex")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    tex_dir = Path(args.tex_dir)
    ordered = resolve_inputs(tex_dir / args.main, tex_dir)

    counter = 0
    label_map = {}
    for name, content in ordered:
        i = 0
        while True:
            m = EQ_RE.search(content, i)
            if not m:
                break
            env, start = m.group(1), m.end()
            end_m = END_RE.search(content, start)
            if not end_m:
                break
            body = content[start:end_m.start()]
            if not m.group(0).endswith('*'):
                if env in ('equation', 'gather', 'multline'):
                    counter += 1
                    for lm in LABEL_RE.finditer(body):
                        label_map[lm.group(1)] = counter
                elif env in ('align', 'eqnarray'):
                    for row in re.split(r'\\\\', body):
                        if NONUMBER_RE.search(row):
                            continue
                        counter += 1
                        for lm in LABEL_RE.finditer(row):
                            label_map[lm.group(1)] = counter
            i = end_m.end()

    lines = [f"{k}={label_map[k]}" for k in sorted(label_map)]
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {len(lines)} labels to {args.out}")
    else:
        print("\n".join(lines))
    print(f"# {len(ordered)} files, {counter} numbered equations", file=__import__("sys").stderr)


if __name__ == "__main__":
    main()
