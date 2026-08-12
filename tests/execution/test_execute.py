"""I-PASS-2, I-SCOPE-1, I-REC-2 — execution integrity."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree, write,
)


class ExecutionTests(unittest.TestCase):
    def test_I_PASS_2_exit0_not_enough(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                expected_outputs=[{
                    "path": "src/out.txt",
                    "sha256": "00" * 32,
                }],
                validation_commands=[{
                    "id": "v1",
                    "command": "python3 -c pass",
                    "expected_exit": 0,
                    "purpose": "smoke",
                }],
            )
            seed_worktree(repo, contract_doc([task]))
            res = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(res.result, "FAIL")
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertNotEqual(states.get("T1"), "PASS")

    def test_I_SCOPE_1_outside_target(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                implementation_targets=["src/out.txt"],
                validation_commands=[{
                    "id": "v1",
                    "command": "python3 -c \"open('leaked.txt','w').write('x')\"",
                    "expected_exit": 0,
                    "purpose": "leak",
                }],
            )
            seed_worktree(repo, contract_doc([task]))
            res = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(res.result, "FAIL")
            self.assertTrue(any("scope violation" in e for e in res.errors))
            self.assertTrue(res.new_evidence)
            self.assertEqual(res.new_evidence[0]["failure_class"], "INTEGRATION")

    def test_empty_cli_allow_intersect_denies(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            res = make_controller(repo, execute_allow=["not-a-contract-tool"]).run(
                dry_run=False, execute=True
            )
            self.assertEqual(res.result, "FAIL")
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertNotEqual(states.get("T1"), "PASS")
            self.assertTrue(res.new_evidence)
            self.assertEqual(res.new_evidence[0]["result"], "BLOCKED")

    def test_execution_contract_records_allowlist(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            res = make_controller(repo).run(dry_run=True, execute=False)
            self.assertTrue(res.contracts)
            ec = res.contracts[0]
            self.assertEqual(ec.get("effective_allowlist"), ["python3"])
            self.assertIsNone(ec.get("cli_allow_tool"))
            self.assertEqual(ec.get("contract_tool_set"), ["python3"])
            refined = make_controller(repo, execute_allow=["python3"]).run(
                dry_run=True, execute=False
            )
            self.assertEqual(refined.contracts[0].get("cli_allow_tool"), ["python3"])
            self.assertEqual(
                refined.contracts[0].get("effective_allowlist"), ["python3"]
            )

    def test_I_REC_2_no_reexec(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            c1 = make_controller(repo)
            r1 = c1.run(dry_run=False, execute=True)
            self.assertEqual(r1.result, "PASS", r1.errors)
            n1 = c1.log.verify_integrity()["trusted_records"]
            r2 = make_controller(repo).run(dry_run=False, execute=True)
            n2 = EvidenceCount(repo)
            self.assertEqual(n1, n2)


def EvidenceCount(repo: Path) -> int:
    from git_up.evidence import EvidenceLog
    return EvidenceLog(repo / ".git-up" / "evidence.jsonl").verify_integrity()[
        "trusted_records"
    ]


if __name__ == "__main__":
    unittest.main()
