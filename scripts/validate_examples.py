#!/usr/bin/env python3
"""Validate workflow YAML in the skill docs and test fixtures against the bundled schema.

Checks:
  * every complete workflow / task-list YAML block in the skill markdown is schema-valid
  * tests/fixtures/valid/*.yaml are schema-valid
  * tests/fixtures/invalid/*.yaml are rejected by the schema

Requires `check-jsonschema` on PATH. Uses only the Python standard library.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = PLUGIN_ROOT / "skills" / "jobworkerp-workflow"
SCHEMA = SKILL_DIR / "references" / "workflow-validation-schema.json"
MARKDOWN_FILES = [
    SKILL_DIR / "SKILL.md",
    SKILL_DIR / "references" / "schema-reference.md",
    SKILL_DIR / "references" / "examples.md",
]
FIXTURES = PLUGIN_ROOT / "tests" / "fixtures"
SKIP_MARKER = "<!-- validate:skip -->"

# Task fragments (`- Name:` lists) are wrapped into a minimal workflow so they can be
# validated in isolation; the task list is nested under `do:` with two extra spaces.
WRAPPER_HEADER = (
    "document:\n"
    '  dsl: "0.0.1"\n'
    "  namespace: default\n"
    "  name: fragment\n"
    '  version: "0.0.1"\n'
    "do:\n"
)

FENCE_RE = re.compile(r"^```yaml\s*$")
# A bare `...` placeholder marks an intentionally incomplete snippet.
PLACEHOLDER_RE = re.compile(r"(^|\s|:)\.\.\.(\s|$)")


@dataclass
class Block:
    source: str
    line: int
    text: str


def extract_blocks(path: Path) -> list[Block]:
    blocks: list[Block] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        if FENCE_RE.match(lines[i]):
            start = i
            prev = next(
                (lines[j].strip() for j in range(i - 1, -1, -1) if lines[j].strip()), ""
            )
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            if prev != SKIP_MARKER:
                blocks.append(
                    Block(
                        str(path.relative_to(PLUGIN_ROOT)),
                        start + 1,
                        "\n".join(body) + "\n",
                    )
                )
        i += 1
    return blocks


def first_content_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return line
    return ""


def to_workflow(text: str) -> str | None:
    """Return a standalone workflow document, or None when the block is only a fragment."""
    if PLACEHOLDER_RE.search(text):
        return None
    head = first_content_line(text)
    if head.startswith("document:"):
        return text
    if head.startswith("- "):
        return WRAPPER_HEADER + "".join(
            f"  {line}\n" if line else "\n" for line in text.splitlines()
        )
    return None


def validate(path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        ["check-jsonschema", "--schemafile", str(SCHEMA), str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


@dataclass
class Report:
    checked: int = 0
    skipped: int = 0
    failures: list[str] = field(default_factory=list)


def check_markdown_examples(report: Report) -> None:
    validated = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for md in MARKDOWN_FILES:
            for block in extract_blocks(md):
                workflow = to_workflow(block.text)
                if workflow is None:
                    report.skipped += 1
                    continue
                target = tmpdir / f"block-{validated}.yaml"
                target.write_text(workflow, encoding="utf-8")
                validated += 1
                report.checked += 1
                ok, out = validate(target)
                if not ok:
                    report.failures.append(
                        f"{block.source}:{block.line}: schema violation\n{out}"
                    )


def check_fixtures(kind: str, report: Report, *, expect_valid: bool) -> None:
    for fixture in sorted((FIXTURES / kind).glob("*.yaml")):
        report.checked += 1
        ok, out = validate(fixture)
        if ok == expect_valid:
            continue
        name = fixture.relative_to(PLUGIN_ROOT)
        report.failures.append(
            f"{name}: expected valid\n{out}"
            if expect_valid
            else f"{name}: expected schema rejection but it passed"
        )


def main() -> int:
    if shutil.which("check-jsonschema") is None:
        print(
            "check-jsonschema is required (pipx install check-jsonschema)",
            file=sys.stderr,
        )
        return 2

    report = Report()
    check_markdown_examples(report)
    check_fixtures("valid", report, expect_valid=True)
    check_fixtures("invalid", report, expect_valid=False)

    for failure in report.failures:
        print(f"FAIL {failure}\n")
    print(
        f"checked={report.checked} skipped_fragments={report.skipped} "
        f"failed={len(report.failures)}"
    )
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
