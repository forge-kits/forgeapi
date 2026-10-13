"""Build the docs site pages from README.md (single source of truth) and CHANGELOG.md.

Run by the mkdocs-gen-files plugin on every ``mkdocs build``/``serve``. Nothing generated
here is committed: edit README.md, then rebuild.

README layout expected: a title, a table of contents, then numbered sections
``## N. Title``. Each numbered section becomes ``<NN>-<slug>.md``; ``###`` headings become
``##`` (the page title is the section title). Fails loudly if README.md and the ``nav`` in
mkdocs.yml disagree, so a new or renamed section cannot silently disappear from the site.
"""
from __future__ import annotations

import re
from pathlib import Path

import mkdocs_gen_files
import yaml

ROOT = Path(__file__).resolve().parent.parent
SECTION_RE = re.compile(r"^## (\d+)\. (.+?)\s*$")


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def shift_headings(lines: list[str]) -> list[str]:
    """Move ### -> ##, #### -> ### ... outside code fences."""
    out, fence = [], False
    for line in lines:
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and re.match(r"^#{3,6} ", line):
            line = line[1:]
        out.append(line)
    return out


def split_sections(text: str) -> tuple[list[str], list[tuple[str, str, list[str]]]]:
    head: list[str] = []
    sections: list[tuple[str, str, list[str]]] = []
    fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else SECTION_RE.match(line)
        if m:
            sections.append((m[1], m[2], []))
        elif sections:
            sections[-1][2].append(line)
        else:
            head.append(line)
    return head, sections


def clean_body(lines: list[str]) -> str:
    while lines and lines[-1].strip() in ("", "---"):  # trailing separators between sections
        lines.pop()
    return "\n".join(shift_headings(lines)).strip() + "\n"


def nav_files() -> set[str]:
    cfg = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8").replace("!!python/name:", "#"))
    found: set[str] = set()

    def walk(node):
        if isinstance(node, str):
            found.add(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(cfg.get("nav", []))
    return found


readme = (ROOT / "README.md").read_text(encoding="utf-8")
head, sections = split_sections(readme)
if not sections:
    raise SystemExit("gen_pages: no '## N. Title' sections found in README.md")

generated = {"index.md", "changelog.md"}

# Landing page: README title + intro, without the table of contents.
intro = []
skip = False
for line in head:
    if line.startswith("## Table of Contents"):
        skip = True
        continue
    if not skip:
        intro.append(line)
with mkdocs_gen_files.open("index.md", "w") as f:
    f.write("\n".join(intro).strip() + "\n\nUse the navigation to browse the sections.\n")

for number, title, body in sections:
    name = f"{int(number):02d}-{slug(title)}.md"
    generated.add(name)
    with mkdocs_gen_files.open(name, "w") as f:
        f.write(f"# {title}\n\n{clean_body(body)}")

with mkdocs_gen_files.open("changelog.md", "w") as f:
    f.write((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))

missing = generated - nav_files()
stale = {n for n in nav_files() if n.endswith(".md")} - generated
if missing or stale:
    raise SystemExit(
        "gen_pages: README sections and mkdocs.yml nav differ.\n"
        f"  in README but not in nav: {sorted(missing)}\n  in nav but not in README: {sorted(stale)}"
    )
