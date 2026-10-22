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
from dataclasses import dataclass
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


def main() -> int:
    if shutil.which("check-jsonschema") is None:
        print(
            "check-jsonschema is required (pipx install check-jsonschema)",
            file=sys.stderr,
        )
        return 2

    failures: list[str] = []
    checked = skipped = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for md in MARKDOWN_FILES:
            for block in extract_blocks(md):
                workflow = to_workflow(block.text)
                if workflow is None:
                    skipped += 1
                    continue
                target = tmpdir / f"block-{checked}.yaml"
                target.write_text(workflow, encoding="utf-8")
                checked += 1
                ok, out = validate(target)
                if not ok:
                    failures.append(
                        f"{block.source}:{block.line}: schema violation\n{out}"
                    )

    for fixture in sorted((FIXTURES / "valid").glob("*.yaml")):
        checked += 1
        ok, out = validate(fixture)
        if not ok:
            failures.append(
                f"{fixture.relative_to(PLUGIN_ROOT)}: expected valid\n{out}"
            )

    for fixture in sorted((FIXTURES / "invalid").glob("*.yaml")):
        checked += 1
        ok, _ = validate(fixture)
        if ok:
            failures.append(
                f"{fixture.relative_to(PLUGIN_ROOT)}: expected schema rejection but it passed"
            )

    for failure in failures:
        print(f"FAIL {failure}\n")
    print(f"checked={checked} skipped_fragments={skipped} failed={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
