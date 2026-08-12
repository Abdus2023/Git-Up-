"""I-COV-1, I-LEDGER-1."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree,
)


class CoverageTests(unittest.TestCase):
    def test_I_COV_1_strict_gap(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(acceptance_criteria=[
                {"id": "c1", "statement": "has validator", "validator": "v1"},
                {"id": "c2", "statement": "missing validator", "validator": ""},
            ])
            seed_worktree(repo, contract_doc([task]))
            res = make_controller(repo).run(dry_run=True)
            states = {c["task_id"]: c for c in res.report["classifications"]}
            self.assertEqual(states["T1"]["effective_state"], "BLOCKED")
            self.assertTrue(
                any("no validator" in d for d in states["T1"]["detail"])
            )

    def test_I_LEDGER_1_ledger_not_authority(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            t1 = minimal_task(id="T1")
            t_uncovered = minimal_task(
                id="T3",
                acceptance_criteria=[],  # insufficient — cannot PASS
                validation_commands=[{
                    "id": "v1", "command": "python3 -c pass",
                    "expected_exit": 0, "purpose": "x",
                }],
            )
            reqs = [{
                "id": "R1",
                "specification_refs": ["docs/SPEC.md"],
                "coverage": [{"task_id": "T1", "obligations": ["all"]}],
            }]
            seed_worktree(repo, contract_doc([t1, t_uncovered], requirements=reqs))
            res = make_controller(repo).run(dry_run=False, execute=True)
            ledger = {r["requirement_id"]: r for r in res.report["requirement_ledger"]}
            self.assertEqual(ledger["R1"]["status"], "SATISFIED")
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            # T3 is not covered and is insufficient; SATISFIED ledger must not PASS it
            self.assertNotEqual(states.get("T3"), "PASS")
            self.assertEqual(states.get("T3"), "BLOCKED")


if __name__ == "__main__":
    unittest.main()
