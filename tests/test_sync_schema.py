"""Tests for scripts/sync-schema.sh argument handling.

The fake upstream holds byte-identical copies of the bundled schemas, so the
real reference files stay unchanged even if the script copies them.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PLUGIN_ROOT / "scripts" / "sync-schema.sh"
REFS = PLUGIN_ROOT / "skills" / "jobworkerp-workflow" / "references"
UPSTREAM_COPIES = {
    "runner/schema/workflow.yaml": REFS / "workflow-schema.yaml",
    "runner/schema/workflow_minimal_fix.json": REFS / "workflow-validation-schema.json",
}


class SyncSchemaArgsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.upstream = Path(tmp.name)
        for upstream_path, bundled in UPSTREAM_COPIES.items():
            target = self.upstream / upstream_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundled, target)

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(SCRIPT), *args], check=False, capture_output=True, text=True
        )

    def test_check_reports_up_to_date(self):
        proc = self.run_script(str(self.upstream), "--check")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("up to date", proc.stdout)

    def test_unknown_option_is_rejected_without_copying(self):
        proc = self.run_script(str(self.upstream), "--chek")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage:", proc.stderr)
        self.assertNotIn("synced", proc.stdout)

    def test_extra_arguments_are_rejected(self):
        proc = self.run_script(str(self.upstream), "--check", "extra")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage:", proc.stderr)

    def test_missing_upstream_argument_is_rejected(self):
        proc = self.run_script()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage:", proc.stderr)


if __name__ == "__main__":
    unittest.main()
