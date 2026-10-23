#!/usr/bin/env python3
"""Validate workflow YAML in the skill docs and test fixtures against the bundled schema.

Checks:
  * every complete workflow / task-list YAML block in the skill markdown is schema-valid
  * tests/fixtures/valid/*.yaml are schema-valid
  * tests/fixtures/invalid/*.yaml are rejected by the schema

Requires `check-jsonschema` on PATH. Uses only the Python standard library.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
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

# Fragments get a minimal `document` so they can be validated in isolation: a block
# starting with `do:` is prefixed as-is, and a task list (`- Name:`) is additionally
# nested under `do:` with two extra spaces.
DOCUMENT_HEADER = (
    "document:\n"
    '  dsl: "0.0.1"\n'
    "  namespace: default\n"
    "  name: fragment\n"
    '  version: "0.0.1"\n'
)
WRAPPER_HEADER = DOCUMENT_HEADER + "do:\n"

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
    if head.startswith("do:"):
        return DOCUMENT_HEADER + text
    if head.startswith("- "):
        return WRAPPER_HEADER + "".join(
            f"  {line}\n" if line else "\n" for line in text.splitlines()
        )
    return None


class Outcome(Enum):
    VALID = "valid"
    REJECTED = "rejected"  # schema violation
    ERROR = "error"  # YAML parse error or the checker itself failed


def format_schema_error(error: dict) -> str:
    text = f"{error.get('path', '$')}: {error.get('message', '')}"
    # The top-level message of a oneOf mismatch is uninformative; the deepest
    # match usually names the offending property.
    deep = error.get("best_deep_match")
    if deep:
        text += f"\n  best match: {deep.get('path', '$')}: {deep.get('message', '')}"
    return text


def classify(stdout: str, stderr: str) -> tuple[Outcome, str]:
    """Interpret `check-jsonschema -o json` output as an outcome and a diagnostic."""
    raw = (stdout + stderr).strip()
    try:
        result = json.loads(stdout)
    except ValueError:
        return Outcome.ERROR, raw
    if result.get("status") == "ok":
        return Outcome.VALID, ""
    parse_errors = result.get("parse_errors") or []
    errors = result.get("errors") or []
    if parse_errors or not errors:
        detail = "\n".join(e.get("message", "") for e in parse_errors)
        return Outcome.ERROR, detail or raw
    return Outcome.REJECTED, "\n".join(format_schema_error(e) for e in errors)


def validate(path: Path) -> tuple[Outcome, str]:
    # JSON output is used because check-jsonschema exits 1 for schema
    # violations, parse errors and its own failures alike.
    proc = subprocess.run(
        ["check-jsonschema", "-o", "json", "--schemafile", str(SCHEMA), str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return classify(proc.stdout, proc.stderr)


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
                outcome, out = validate(target)
                if outcome is Outcome.VALID:
                    continue
                reason = (
                    "schema violation"
                    if outcome is Outcome.REJECTED
                    else "could not be validated"
                )
                report.failures.append(f"{block.source}:{block.line}: {reason}\n{out}")


def check_fixtures(kind: str, report: Report, *, expect_valid: bool) -> None:
    for fixture in sorted((FIXTURES / kind).glob("*.yaml")):
        report.checked += 1
        outcome, out = validate(fixture)
        name = fixture.relative_to(PLUGIN_ROOT)
        if expect_valid:
            if outcome is not Outcome.VALID:
                report.failures.append(f"{name}: expected valid\n{out}")
        elif outcome is Outcome.VALID:
            report.failures.append(f"{name}: expected schema rejection but it passed")
        elif outcome is Outcome.ERROR:
            # Only a schema violation proves the fixture is rejected for the
            # intended reason; a parse error or checker failure proves nothing.
            report.failures.append(
                f"{name}: expected schema rejection but validation did not run\n{out}"
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
