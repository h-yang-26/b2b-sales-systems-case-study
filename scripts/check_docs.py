"""Documentation checks for the fictional B2B case study.

Checks, using only the standard library (Python 3.11+):
  1. every deliverable file exists and the JSON parses;
  2. local Markdown links resolve (and heading anchors exist);
  3. identifiers like OPP-1001 or SO-3001 used in documents exist in the JSON,
     and every identifier in the JSON is used in at least one document;
  4. Mermaid fences are closed and each architecture diagram has content;
  5. key scenario quantities appear in the documents that must state them.

Usage:
    python scripts/check_docs.py

Exit status 0 when all checks pass, 1 otherwise. This does not render Mermaid.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "examples" / "fictional-order-scenario.json"
DELIVERABLES = [
    "README.md",
    "docs/sales-lifecycle.md",
    "docs/data-model.md",
    "docs/system-architecture.md",
    "docs/design-decisions.md",
    "docs/business-metrics.md",
    "examples/fictional-order-scenario.json",
]
DOCS = [p for p in DELIVERABLES if p.endswith(".md")]
ID_PATTERN = re.compile(r"\b(?:ACC|LEAD|OPP|QUO|QL|SO|OL|SHP|PO|RSV|INV)-\d{3,4}(?:-\d+)?\b")
LINK_PATTERN = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)")


def slugify(heading):
    """GitHub-style anchor for a heading (enough for plain headings)."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s", "-", text)


def headings(path):
    out = set()
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("#"):
            out.add(slugify(line.lstrip("#")))
    return out


def check_files_exist():
    return [f"missing deliverable: {p}" for p in DELIVERABLES if not (ROOT / p).is_file()]


def check_links():
    problems = []
    for rel in DOCS:
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for target in LINK_PATTERN.findall(text):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # http:, https:, mailto:
                continue
            file_part, _, anchor = target.partition("#")
            dest = path if not file_part else (path.parent / file_part).resolve()
            if not dest.exists():
                problems.append(f"{rel}: broken link target {target!r}")
            elif anchor and dest.suffix == ".md" and anchor not in headings(dest):
                problems.append(f"{rel}: anchor #{anchor} not found in {dest.name}")
    return problems


def json_identifiers(data):
    return set(ID_PATTERN.findall(json.dumps(data)))


def check_identifiers(data):
    problems = []
    known = json_identifiers(data)
    used = set()
    for rel in DOCS:
        found = set(ID_PATTERN.findall((ROOT / rel).read_text(encoding="utf-8")))
        used |= found
        for ident in sorted(found - known):
            problems.append(f"{rel}: identifier {ident} is not in the scenario JSON")
    for ident in sorted(known - used):
        problems.append(f"identifier {ident} appears in the JSON but in no document")
    return problems


def check_mermaid():
    problems = []
    text = (ROOT / "docs/system-architecture.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\n(.*?)```", text, flags=re.S)
    if len(blocks) != 2:
        problems.append(f"system-architecture.md: expected 2 mermaid blocks, found {len(blocks)}")
    if text.count("```") % 2:
        problems.append("system-architecture.md: unbalanced code fences")
    for i, block in enumerate(blocks, start=1):
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines or not lines[0].startswith("flowchart"):
            problems.append(f"mermaid block {i}: does not start with a flowchart declaration")
        if len(lines) < 5:
            problems.append(f"mermaid block {i}: suspiciously short")
        if len(re.findall(r"^\s*subgraph\b", block, flags=re.M)) != len(re.findall(r"^\s*end\s*$", block, flags=re.M)):
            problems.append(f"mermaid block {i}: subgraph/end mismatch")
        if block.count("[") != block.count("]") or block.count("{") != block.count("}"):
            problems.append(f"mermaid block {i}: unbalanced brackets")
        if block.count('"') % 2:
            problems.append(f"mermaid block {i}: unbalanced quotes")
    return problems


def check_required_statements(data):
    """Documents that must state the scenario quantities must agree with the JSON."""
    problems = []
    summary = data["quantity_summary_at_snapshot"]
    pairs = {
        "README.md": ["hypothetical systems-design exercise", "2 - 1", "What I would build next (hypothetically)"],
        "docs/sales-lifecycle.md": ["4 units quoted", "2 units ordered", "1 unit shipped", "= 2 - 1 = 1"],
        "docs/data-model.md": ["`remaining_order_quantity`", "committed demand", "missing ETA is not a zero-day ETA"],
        "docs/design-decisions.md": ["2 - 1 = 1", "ADR-001", "ADR-002", "ADR-003"],
        "docs/business-metrics.md": ["2 / 4 = 50%", "5 / 18", "4 / 5 = 80%", "2 / 4 = 50%"],
    }
    for rel, needles in pairs.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needle in needles:
            if needle.lower() not in text.lower():
                problems.append(f"{rel}: expected to mention {needle!r}")
    if (summary["quoted_quantity"], summary["ordered_quantity"], summary["shipped_quantity"],
            summary["remaining_order_quantity"]) != (4, 2, 1, 1):
        problems.append("scenario JSON no longer has quote 4 / order 2 / ship 1 / remaining 1")
    arch = (ROOT / "docs/system-architecture.md").read_text(encoding="utf-8")
    for needle in ("4 units quoted", "2 units ordered", "1 unit shipped", "Remaining order quantity = 2 - 1 = 1"):
        if needle not in arch:
            problems.append(f"system-architecture.md: process diagram should contain {needle!r}")
    return problems


def main():
    problems = check_files_exist()
    if problems:  # nothing else is meaningful without the files
        report(problems)
        return 1
    try:
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report([f"JSON syntax error in {JSON_PATH.name}: {exc}"])
        return 1
    problems += check_links()
    problems += check_identifiers(data)
    problems += check_mermaid()
    problems += check_required_statements(data)
    report(problems)
    return 1 if problems else 0


def report(problems):
    if not problems:
        print("check_docs: PASS (files, JSON syntax, links, identifiers, mermaid structure, key statements)")
        print("Note: Mermaid diagrams were checked structurally only, not rendered.")
        return
    print(f"check_docs: FAIL ({len(problems)} problem(s))")
    for p in problems:
        print(f"  - {p}")


if __name__ == "__main__":
    sys.exit(main())
