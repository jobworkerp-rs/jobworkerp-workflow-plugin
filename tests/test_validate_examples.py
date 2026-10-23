"""Regression tests for scripts/validate_examples.py.

`check-jsonschema` is replaced by a stub on PATH that rejects any file
containing the word INVALID, so the tests run without the real tool.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_examples.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_examples", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ve = load_module()

STUB = """#!/bin/sh
# argv: --schemafile <schema> <target>
# Record what was validated (order and content) so tests observe it from outside.
printf '%s\\n' "$3" >> "$STUB_LOG"
cp "$3" "$STUB_CAPTURE/"
if grep -q INVALID "$3"; then
  echo "stub rejected $(basename "$3")"
  exit 1
fi
echo ok
"""

FULL_WORKFLOW = textwrap.dedent(
    """\
    document:
      dsl: "0.0.1"
      namespace: default
      name: full
      version: "0.0.1"
    do:
      - a:
          set:
            x: 1
    """
)


class PluginRootTestCase(unittest.TestCase):
    """Runs each test against a temporary directory acting as the plugin root."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.patch(ve, "PLUGIN_ROOT", self.root)

    def patch(self, target, attr: str, value) -> None:
        patcher = mock.patch.object(target, attr, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_doc(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path


class ExtractBlocksTest(PluginRootTestCase):
    def test_returns_yaml_blocks_with_source_and_fence_line(self):
        md = self.write_doc(
            "doc.md",
            """\
            # Title

            ```yaml
            - a: {}
            ```

            ```bash
            echo not yaml
            ```

            ```yaml
            document: {}
            ```
            """,
        )
        blocks = ve.extract_blocks(md)
        self.assertEqual(
            [(b.source, b.line) for b in blocks], [("doc.md", 3), ("doc.md", 11)]
        )
        self.assertEqual(blocks[0].text, "- a: {}\n")
        self.assertEqual(blocks[1].text, "document: {}\n")

    def test_skip_marker_excludes_next_block_even_after_blank_line(self):
        md = self.write_doc(
            "doc.md",
            """\
            <!-- validate:skip -->

            ```yaml
            - skipped: {}
            ```

            ```yaml
            - kept: {}
            ```
            """,
        )
        blocks = ve.extract_blocks(md)
        self.assertEqual([b.text for b in blocks], ["- kept: {}\n"])


class ToWorkflowTest(unittest.TestCase):
    def test_full_workflow_is_returned_unchanged(self):
        self.assertEqual(ve.to_workflow(FULL_WORKFLOW), FULL_WORKFLOW)

    def test_task_fragment_is_wrapped_and_indented(self):
        fragment = "- a:\n    set:\n      x: 1\n\n- b:\n    wait: { seconds: 1 }\n"
        expected = (
            ve.WRAPPER_HEADER
            + "  - a:\n      set:\n        x: 1\n\n  - b:\n      wait: { seconds: 1 }\n"
        )
        self.assertEqual(ve.to_workflow(fragment), expected)

    def test_leading_comments_and_blank_lines_are_ignored_for_detection(self):
        fragment = "\n# comment\n- a: {}\n"
        self.assertEqual(
            ve.to_workflow(fragment), ve.WRAPPER_HEADER + "\n  # comment\n  - a: {}\n"
        )

    def test_placeholder_marks_block_as_fragment(self):
        self.assertIsNone(ve.to_workflow("- a:\n    run: ...\n"))

    def test_other_fragments_are_skipped(self):
        for text in [
            "run:\n  runner: {}\n",
            "do:\n  - a: {}\n",
            "# only comment\n",
            "",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(ve.to_workflow(text))


class MainTest(PluginRootTestCase):
    def setUp(self):
        super().setUp()
        bindir = self.root / "bin"
        bindir.mkdir()
        stub = bindir / "check-jsonschema"
        stub.write_text(STUB, encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.log = self.root / "stub.log"
        self.capture = self.root / "captured"
        self.capture.mkdir()

        env = {
            "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
            "STUB_LOG": str(self.log),
            "STUB_CAPTURE": str(self.capture),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.patch(ve, "SCHEMA", self.root / "schema.json")
        self.patch(ve, "FIXTURES", self.root / "fixtures")

    def set_docs(self, *docs: str) -> None:
        paths = [self.write_doc(f"doc{i}.md", text) for i, text in enumerate(docs)]
        self.patch(ve, "MARKDOWN_FILES", paths)

    def add_fixture(self, kind: str, name: str, text: str) -> None:
        directory = self.root / "fixtures" / kind
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(text, encoding="utf-8")

    def run_main(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ve.main()
        return code, out.getvalue(), err.getvalue()

    def test_missing_checker_returns_2(self):
        with mock.patch.object(ve.shutil, "which", return_value=None):
            code, out, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("check-jsonschema is required", err)

    def test_success_reports_counts_and_returns_0(self):
        self.set_docs(
            """\
            ```yaml
            - a: {}
            ```

            ```yaml
            run: {}
            ```
            """
        )
        self.add_fixture("valid", "ok.yaml", FULL_WORKFLOW)
        self.add_fixture("invalid", "bad.yaml", "INVALID\n")
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(out, "checked=3 skipped_fragments=1 failed=0\n")

    def test_failures_keep_order_and_diagnostics_and_return_1(self):
        self.set_docs(
            """\
            ```yaml
            - INVALID: {}
            ```
            """,
            """\
            ```yaml
            - fine: {}
            ```
            """,
        )
        self.add_fixture("valid", "b.yaml", "INVALID\n")
        self.add_fixture("valid", "a.yaml", "INVALID\n")
        self.add_fixture("invalid", "accepted.yaml", FULL_WORKFLOW)
        self.add_fixture("invalid", "rejected.yaml", "INVALID\n")
        code, out, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(
            out,
            "FAIL doc0.md:1: schema violation\nstub rejected block-0.yaml\n\n"
            "FAIL fixtures/valid/a.yaml: expected valid\nstub rejected a.yaml\n\n"
            "FAIL fixtures/valid/b.yaml: expected valid\nstub rejected b.yaml\n\n"
            "FAIL fixtures/invalid/accepted.yaml: expected schema rejection but it passed\n\n"
            "checked=6 skipped_fragments=0 failed=4\n",
        )

    def test_markdown_temp_files_are_removed_and_fixtures_checked_in_order(self):
        self.set_docs(
            """\
            ```yaml
            - a: {}
            ```

            ```yaml
            - b: {}
            ```
            """
        )
        self.add_fixture("valid", "z.yaml", FULL_WORKFLOW)
        self.add_fixture("valid", "m.yaml", FULL_WORKFLOW)
        self.add_fixture("invalid", "x.yaml", "INVALID\n")
        code, _, _ = self.run_main()
        self.assertEqual(code, 0)
        targets = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [Path(t).name for t in targets],
            ["block-0.yaml", "block-1.yaml", "m.yaml", "z.yaml", "x.yaml"],
        )
        for block_file in targets[:2]:
            self.assertFalse(Path(block_file).exists())

    def test_wrapped_fragment_is_what_gets_validated(self):
        self.set_docs("```yaml\n- a: {}\n```\n")
        code, _, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(
            (self.capture / "block-0.yaml").read_text(encoding="utf-8"),
            ve.WRAPPER_HEADER + "  - a: {}\n",
        )


if __name__ == "__main__":
    unittest.main()
