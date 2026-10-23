"""Regression tests for scripts/validate_examples.py.

`check-jsonschema` is replaced by a stub on PATH that mimics its `-o json`
output, so the tests run without the real tool. The stub decides the result
from markers in the validated file: INVALID (schema violation), BROKEN (YAML
parse error) or CRASH (tool failure without JSON output).
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
# The validated file is the last argument.
for target; do :; done
name=$(basename "$target")
# Record what was validated (order and content) so tests observe it from outside.
printf '%s\\n' "$target" >> "$STUB_LOG"
cp "$target" "$STUB_CAPTURE/"
if grep -q CRASH "$target"; then
  echo "Traceback: boom" >&2
  exit 1
elif grep -q BROKEN "$target"; then
  printf '{"status":"fail","errors":[],"parse_errors":[{"filename":"%s","message":"Failed to parse %s"}]}' "$target" "$name"
  exit 1
elif grep -q INVALID "$target"; then
  printf '{"status":"fail","errors":[{"filename":"%s","path":"$.do[0]","message":"stub rejected %s","best_deep_match":{"path":"$.do[0].run","message":"deep reason"}}],"parse_errors":[]}' "$target" "$name"
  exit 1
fi
printf '{"status":"ok","errors":[]}'
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

    def test_do_fragment_gets_document_header(self):
        fragment = "# loop\ndo:\n  - a: {}\n"
        self.assertEqual(ve.to_workflow(fragment), ve.DOCUMENT_HEADER + fragment)

    def test_other_fragments_are_skipped(self):
        for text in [
            "run:\n  runner: {}\n",
            "# only comment\n",
            "",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(ve.to_workflow(text))


class ClassifyTest(unittest.TestCase):
    def test_ok_status_is_valid(self):
        self.assertEqual(
            ve.classify('{"status": "ok", "errors": []}', ""), (ve.Outcome.VALID, "")
        )

    def test_schema_errors_are_rejected_with_path_and_deepest_match(self):
        stdout = (
            '{"status": "fail", "parse_errors": [], "errors": ['
            '{"path": "$.do[0]", "message": "top",'
            ' "best_deep_match": {"path": "$.do[0].run", "message": "deep"}},'
            '{"path": "$.use", "message": "other"}]}'
        )
        self.assertEqual(
            ve.classify(stdout, ""),
            (
                ve.Outcome.REJECTED,
                "$.do[0]: top\n  best match: $.do[0].run: deep\n$.use: other",
            ),
        )

    def test_parse_errors_are_errors_not_rejections(self):
        stdout = '{"status": "fail", "errors": [], "parse_errors": [{"message": "bad yaml"}]}'
        self.assertEqual(ve.classify(stdout, ""), (ve.Outcome.ERROR, "bad yaml"))

    def test_failure_without_any_error_detail_falls_back_to_raw_output(self):
        stdout = '{"status": "fail", "errors": [], "parse_errors": []}'
        self.assertEqual(
            ve.classify(stdout, "warn\n"), (ve.Outcome.ERROR, stdout + "warn")
        )

    def test_non_json_output_is_an_error_with_raw_output(self):
        self.assertEqual(
            ve.classify("", "Traceback: boom\n"), (ve.Outcome.ERROR, "Traceback: boom")
        )


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
            "FAIL doc0.md:1: schema violation\n"
            "$.do[0]: stub rejected block-0.yaml\n"
            "  best match: $.do[0].run: deep reason\n\n"
            "FAIL fixtures/valid/a.yaml: expected valid\n"
            "$.do[0]: stub rejected a.yaml\n"
            "  best match: $.do[0].run: deep reason\n\n"
            "FAIL fixtures/valid/b.yaml: expected valid\n"
            "$.do[0]: stub rejected b.yaml\n"
            "  best match: $.do[0].run: deep reason\n\n"
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

    def test_invalid_fixture_counts_only_schema_violations_as_rejection(self):
        self.add_fixture("invalid", "broken.yaml", "BROKEN\n")
        self.add_fixture("invalid", "crash.yaml", "CRASH\n")
        self.add_fixture("invalid", "rejected.yaml", "INVALID\n")
        self.set_docs()
        code, out, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(
            out,
            "FAIL fixtures/invalid/broken.yaml: "
            "expected schema rejection but validation did not run\n"
            "Failed to parse broken.yaml\n\n"
            "FAIL fixtures/invalid/crash.yaml: "
            "expected schema rejection but validation did not run\n"
            "Traceback: boom\n\n"
            "checked=3 skipped_fragments=0 failed=2\n",
        )

    def test_markdown_block_that_cannot_be_validated_is_reported(self):
        self.set_docs("```yaml\n- BROKEN: {}\n```\n")
        code, out, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(
            out,
            "FAIL doc0.md:1: could not be validated\n"
            "Failed to parse block-0.yaml\n\n"
            "checked=1 skipped_fragments=0 failed=1\n",
        )

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
