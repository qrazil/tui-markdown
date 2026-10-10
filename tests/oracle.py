#!/usr/bin/env python3
"""The visible-text oracle.

    python3 tests/oracle.py T_ORACLE_BINARY CASES_FILE

Every case in CASES_FILE (`=== name` then the markdown) is shown by the
viewer's layout at two widths and rendered to HTML by term-markdown. The text
of the HTML (tags removed, entities decoded, an image's alt kept) must equal
the text of the rows (decoration such as bullets and borders left out), once
all whitespace is taken out of both: the viewer may wrap, indent and join
lines however it likes, but it may not lose, add or reorder a character.

Prints one `ok`/`FAIL` line per case and width, and a last line
`N passed, M failed`. Exit status 1 when anything failed.
"""
import html.parser
import os
import re
import subprocess
import sys
import tempfile
import unicodedata


class Text(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.parts.append(dict(attrs).get("alt") or "")


def html_text(source):
    parser = Text()
    parser.feed(source)
    parser.close()
    return "".join(parser.parts)


def squeeze(text):
    return re.sub(r"\s+", "", text)


def cases(path):
    found = []
    name, body = None, []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("=== "):
                if name is not None:
                    found.append((name, "".join(body)))
                name, body = line[4:].strip(), []
            else:
                body.append(line)
    if name is not None:
        found.append((name, "".join(body)))
    return found


def source_of(body):
    # `\uXXXX` and `\r\n` in the cases file stand for the characters, so the
    # file itself stays readable and ASCII-clean where it matters.
    body = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), body)
    body = body.replace("\\r\\n", "\r\n")
    return body.rstrip("\n") + "\n" if body.strip() else ""


def parse(output):
    sections = {}
    key = None
    for line in output.split("\n"):
        if line.startswith("@@@"):
            kind, _, path = line[3:].partition(" ")
            key = (kind, path)
            sections[key] = []
        elif key is not None:
            sections[key].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def main():
    binary, cases_file = sys.argv[1], sys.argv[2]
    passed = failed = 0
    with tempfile.TemporaryDirectory() as work:
        listing = []
        for name, body in cases(cases_file):
            path = os.path.join(work, name + ".md")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(source_of(body))
            listing.append((name, path))
        for width in (40, 9):
            run = subprocess.run(
                [binary, str(width)] + [p for _, p in listing],
                capture_output=True, text=True, encoding="utf-8")
            if run.returncode != 0:
                print("FAIL oracle program exited %d: %s" % (run.returncode, run.stderr.strip()[:200]))
                failed += 1
                continue
            sections = parse(run.stdout)
            for name, path in listing:
                shown = squeeze(sections.get(("TEXT", path), "<missing>"))
                want = squeeze(html_text(sections.get(("HTML", path), "<missing>")))
                label = "%s @%d" % (name, width)
                is_same = unicodedata.normalize("NFC", shown) == unicodedata.normalize("NFC", want)
                if not is_same and name.startswith("table"):
                    # A table's cells wrap side by side, so a row of the screen
                    # reads across the cells: the order differs by design, the
                    # characters may not.
                    is_same = sorted(unicodedata.normalize("NFC", shown)) == sorted(unicodedata.normalize("NFC", want))
                    label += " (same characters)"
                if is_same:
                    passed += 1
                    print("ok   " + label)
                else:
                    failed += 1
                    print("FAIL %s: viewer [%s] html [%s]" % (label, shown[:90], want[:90]))
    print("%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


sys.exit(main())
