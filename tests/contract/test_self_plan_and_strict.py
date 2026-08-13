"""Self-plan emits the product contract; validate --strict is fail-closed."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import emit_contract_file
from git_up.cli import main
from git_up.contract import load_contract
from tests.support import ROOT, init_repo, make_controller, write


class SelfPlanTests(unittest.TestCase):
    def test_self_plan_classifies_ready_in_this_repo(self):
        plan = ROOT / "docs" / "plans" / "self.md"
        self.assertTrue(plan.is_file())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.json"
            emit_contract_file(plan, out)
            loaded = load_contract(out)
            self.assertEqual(loaded.provenance.get("producer"),
                             "git-up.adapter.plan")
            self.assertTrue(loaded.provenance.get("source_identity"))
            res = make_controller(ROOT, contract_path=out).run(dry_run=True)
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertEqual(states.get("T-SPEC18"), "READY")

    def test_strict_validate_blocks_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            write(repo / "docs" / "SPEC.md", "x\n")
            path = repo / "thin.json"
            path.write_text(json.dumps({
                "schema_version": "git-up.contract.v0.1",
                "policy": {"failure_mode": "fail_closed",
                           "concurrency": "exclusive"},
                "tasks": [{"id": "T1", "title": "empty"}],
            }), encoding="utf-8")
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main([
                    "--contract", str(path),
                    "--repo-root", str(repo),
                    "contract", "validate", "--strict",
                ])
            finally:
                sys.stdout = old
            data = json.loads(buf.getvalue())
            self.assertEqual(code, 2, data)
            self.assertIn("T1", data.get("insufficient_tasks") or [])


if __name__ == "__main__":
    unittest.main()
