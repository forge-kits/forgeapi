"""Build CHANGELOG.md from git tags and commit subjects (Conventional Commits).

    python scripts/gen_changelog.py            # rewrite CHANGELOG.md
    python scripts/gen_changelog.py --stdout   # print instead

Commits after the newest tag go under "Unreleased". Version-bump commits, merge commits and
internal notes (audit, CLAUDE.md) are skipped. Subjects that do not follow ``type(scope): text`` land in "Other".
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_URL = "https://github.com/forge-kits/forgeapi"
SECTIONS = [
    ("feat", "Features"),
    ("fix", "Fixes"),
    ("perf", "Performance"),
    ("refactor", "Refactoring"),
    ("docs", "Documentation"),
    ("test", "Tests"),
    ("chore", "Maintenance"),
    ("ci", "Maintenance"),
    ("build", "Maintenance"),
    ("style", "Maintenance"),
    ("other", "Other"),
]
ORDER = list(dict.fromkeys(title for _, title in SECTIONS))
SUBJECT_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<text>.+)$")
BUMP_RE = re.compile(r"^(chore|release)(\([^)]*\))?:\s*(bump|release)\b.*version", re.I)
# Internal process notes (audit rounds, assistant config) have no value for users of the library
# and the changelog is public, so they are left out.
INTERNAL_RE = re.compile(r"\baudit\b|CLAUDE\.md", re.I)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def version_key(tag: str) -> tuple[int, ...]:
    return tuple(int(p) for p in tag.lstrip("v").split("."))


def tags() -> list[str]:
    found = [t for t in git("tag").split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    return sorted(found, key=version_key)


def commits(rev_range: str) -> list[tuple[str, str]]:
    out = git("log", "--no-merges", "--format=%h%x09%s", rev_range)
    rows = [line.split("\t", 1) for line in out.splitlines() if "\t" in line]
    return [(sha, subject) for sha, subject in rows]


def render_group(rows: list[tuple[str, str]]) -> str:
    grouped: dict[str, list[str]] = defaultdict(list)
    for sha, subject in rows:
        if BUMP_RE.match(subject) or INTERNAL_RE.search(subject):
            continue
        m = SUBJECT_RE.match(subject)
        if m:
            kind = m["type"] if m["type"] in dict(SECTIONS) else "other"
            text = m["text"]
            scope = f"**{m['scope']}:** " if m["scope"] else ""
            bang = "**BREAKING** " if m["breaking"] else ""
        else:
            kind, text, scope, bang = "other", subject, "", ""
        text = text[0].upper() + text[1:] if text else text
        title = dict(SECTIONS)[kind]
        grouped[title].append(f"- {bang}{scope}{text} ([`{sha}`]({REPO_URL}/commit/{sha}))")
    lines: list[str] = []
    for title in ORDER:
        if grouped.get(title):
            lines += [f"### {title}", "", *grouped[title], ""]
    return "\n".join(lines)


def build() -> str:
    all_tags = tags()
    parts = [
        "# Changelog\n",
        "Generated from git history by `scripts/gen_changelog.py` "
        "(Conventional Commits). Do not edit by hand.\n",
    ]
    unreleased = commits(f"{all_tags[-1]}..HEAD") if all_tags else []
    body = render_group(unreleased) if unreleased else ""
    if body.strip():
        parts += ["## Unreleased\n", body]
    for i in range(len(all_tags) - 1, -1, -1):
        tag = all_tags[i]
        prev = all_tags[i - 1] if i else None
        date = git("log", "-1", "--format=%cs", tag).strip()
        rows = commits(f"{prev}..{tag}" if prev else tag)
        body = render_group(rows)
        parts.append(f"## [{tag.lstrip('v')}]({REPO_URL}/releases/tag/{tag}) - {date}\n")
        parts.append(body if body.strip() else "_No notable changes._\n")
    return "\n".join(parts).rstrip() + "\n"


if __name__ == "__main__":
    text = build()
    if "--stdout" in sys.argv:
        sys.stdout.write(text)
    else:
        Path(__file__).resolve().parent.parent.joinpath("CHANGELOG.md").write_text(text, encoding="utf-8")
        print("CHANGELOG.md written")
