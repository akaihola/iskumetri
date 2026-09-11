#!/usr/bin/env python3
"""Check that TASKS.md keeps each issue bullet under exactly one heading.

Usage: python3 tools/check_tasks_md.py TASKS.md

The script reads only the issue-tracking part of the file, from the
first `## ` heading up to the `---` line before `## Rules`. It ignores
that later part, because it holds rule text, not issue bullets.

The script prints each duplicated bullet and the headings it is under.
It exits with status 1 if it finds a duplicate, else status 0.
"""
import re
import sys


def read_issue_headings(path):
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()

    heading = None
    entries = []  # list of {"heading": ..., "text": ...}, one per bullet
    current_entry = None

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if line.strip() == "---":
            break
        heading_match = re.match(r"^## (.+)", line)
        if heading_match:
            heading = heading_match.group(1).strip()
            current_entry = None
            continue
        if heading is None:
            continue
        bullet_match = re.match(r"^- (\[[^\]]*\] )?(.+)", line)
        if bullet_match:
            text = bullet_match.group(2).strip()
            current_entry = {"heading": heading, "text": text}
            entries.append(current_entry)
            continue
        continuation_match = re.match(r"^  (\S.*)", line)
        if continuation_match and current_entry is not None:
            extra = continuation_match.group(1).strip()
            current_entry["text"] = current_entry["text"] + " " + extra
        else:
            current_entry = None

    bullets = {}  # normalized full bullet text -> list of entries
    for entry in entries:
        bullets.setdefault(entry["text"], []).append(entry)

    return bullets


def find_duplicates(bullets):
    duplicates = []
    for entries in bullets.values():
        headings = {entry["heading"] for entry in entries}
        if len(headings) > 1:
            duplicates.append(entries)
    return duplicates


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 tools/check_tasks_md.py <path-to-TASKS.md>")
        return 2

    path = sys.argv[1]
    bullets = read_issue_headings(path)
    duplicates = find_duplicates(bullets)

    if not duplicates:
        print("OK: each issue bullet is under exactly one heading.")
        return 0

    for entries in duplicates:
        headings = sorted({entry["heading"] for entry in entries})
        print("DUPLICATE BULLET across headings: " + ", ".join(headings))
        print("  " + entries[0]["text"])

    return 1


if __name__ == "__main__":
    sys.exit(main())
