"""verify emits a derived predicate breakdown (ADR-0014)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.cli import main
from tests.support import init_repo, make_controller, seed_worktree


class VerifyTests(unittest.TestCase):
    def test_verify_dry_run_explains_not_pass(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main([
                    "--contract", str(repo / "git-up.contract.json"),
                    "--repo-root", str(repo),
                    "verify", "--dry-run",
                ])
            finally:
                sys.stdout = old
            data = json.loads(buf.getvalue())
            self.assertEqual(code, 0, data)
            self.assertEqual(data.get("mode"), "verify")
            self.assertTrue(data.get("advisory"))
            pred = data.get("predicate") or []
            self.assertEqual(len(pred), 1)
            self.assertEqual(pred[0]["task_id"], "T1")
            self.assertFalse(pred[0]["would_pass"])
            self.assertTrue(pred[0]["closure_gaps"])

    def test_verify_after_run_would_pass(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            r = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(r.result, "PASS", r.errors)
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main([
                    "--contract", str(repo / "git-up.contract.json"),
                    "--repo-root", str(repo),
                    "verify", "--dry-run",
                ])
            finally:
                sys.stdout = old
            data = json.loads(buf.getvalue())
            self.assertEqual(code, 0, data)
            self.assertTrue(data["predicate"][0]["would_pass"])


if __name__ == "__main__":
    unittest.main()
