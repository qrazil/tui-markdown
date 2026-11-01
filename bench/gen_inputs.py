#!/usr/bin/env python3
"""Writes the benchmark's markdown files into <dir>:  python3 -I bench/gen_inputs.py <dir> <path-to-a-README.md>

readme.md   a copy of the given README (README-sized: a few KB)
mixed-50k.md   ~50 KB of headings, paragraphs, nested lists, tables, code blocks (several languages), links, emoji, CJK
mixed-1m.md    the same pattern to ~1 MB (synthetic: every section is different text, so nothing repeats exactly)
Deterministic: no clock, no random.
"""
import os, shutil, sys

CODE = {
    "rust": 'fn main() {\n    let v: Vec<u32> = (0..%d).map(|x| x * 2).collect();\n    println!("{:?}", v.iter().sum::<u32>());\n}\n',
    "python": 'def fib(n):\n    a, b = 0, 1\n    for _ in range(n + %d):\n        a, b = b, a + b\n    return a\n\nprint(fib(30))  # comment\n',
    "go": 'package main\n\nimport "fmt"\n\nfunc main() {\n\tfor i := 0; i < %d; i++ {\n\t\tfmt.Println("hello", i)\n\t}\n}\n',
    "sh": '#!/bin/sh\nset -eu\nfor f in *.md; do\n  echo "file $f %d"\ndone\n',
    "json": '{\n  "name": "item-%d",\n  "tags": ["a", "b"],\n  "nested": {"ok": true, "n": 3.5}\n}\n',
}
LANGS = list(CODE)

def section(i):
    lang = LANGS[i % len(LANGS)]
    out = []
    out.append("## Section %d: the %s notes\n" % (i, lang))
    out.append("Paragraph %d has **bold text**, *emphasis*, `inline code`, ~~strikethrough~~ and a [link to section %d](https://example.com/s/%d). "
               "It is long enough to wrap across several lines in a terminal of ordinary width, because a renderer that wraps badly is a renderer that shows. "
               "Emoji \U0001F680 \U0001F468‍\U0001F469‍\U0001F467 ❤️ and CJK: 日本語のテキスト、中文文字、한국어 text %d.\n" % (i, (i * 7) % 50, i, i))
    out.append("### Lists\n")
    out.append("- first item %d\n  - nested a\n    - nested deeper %d\n    - nested deeper b\n  - nested b with `code`\n- second item\n  1. ordered one\n  2. ordered two\n- [ ] task open\n- [x] task done\n" % (i, i))
    out.append("> **Note**\n> A block quote in section %d that also wraps over a line or two to see how the quote bar is carried along.\n" % i)
    out.append("| name | value | notes |\n|:-----|------:|:-----:|\n| alpha %d | %d | plain |\n| beta | %d | 日本語 |\n| gamma | 3 | `code` and **bold** |\n" % (i, i, i * 3))
    out.append("```%s\n%s```\n" % (lang, CODE[lang] % (i % 90)))
    out.append("---\n")
    return "\n".join(out)

def build(target_bytes):
    parts = ["# Benchmark document\n\nFront text with a [reference][r] and an image ![alt text](a.png).\n\n[r]: https://example.com/ref\n"]
    size, i = len(parts[0].encode()), 0
    while size < target_bytes:
        s = section(i)
        parts.append(s)
        size += len(s.encode())
        i += 1
    return "\n".join(parts)

d = sys.argv[1]
os.makedirs(d, exist_ok=True)
shutil.copy(sys.argv[2], d + "/readme.md")
for name, n in (("mixed-50k.md", 50 * 1024), ("mixed-1m.md", 1024 * 1024)):
    open(d + "/" + name, "w", encoding="utf-8").write(build(n))
