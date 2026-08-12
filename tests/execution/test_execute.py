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

    def test_flag_dotdot_is_blocked_not_executed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                validation_commands=[{
                    "id": "v1",
                    "command": "python3 --file=../secret",
                    "expected_exit": 0,
                    "purpose": "smuggle",
                }],
            )
            seed_worktree(repo, contract_doc([task]))
            ctrl = make_controller(repo)
            res = ctrl.run(dry_run=False, execute=True)
            self.assertEqual(res.result, "FAIL")
            self.assertTrue(res.new_evidence)
            self.assertEqual(res.new_evidence[0]["result"], "BLOCKED")
            self.assertEqual(ctrl.store.get("T1").state, "BLOCKED")

    def test_execution_contract_records_allowlist(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            res = make_controller(repo).run(dry_run=True, execute=False)
            self.assertTrue(res.contracts)
            ec = res.contracts[0]
            self.assertIn("command_id", ec.get("required_evidence") or [])
            self.assertIn("observed_delta", ec.get("required_evidence") or [])
            self.assertIn("target_hashes", ec.get("required_evidence") or [])
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

    def test_unsafe_command_is_in_progress_blocked(self):
        """Spec 08: safety failure before VALIDATING is BLOCKED, not FAIL."""
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                allowed_tools=["bash", "python3"],
                required_tools=["python3"],
                validation_commands=[{
                    "id": "v1",
                    "command": "bash -c echo hi",
                    "expected_exit": 0,
                    "purpose": "denied-shell",
                }],
            )
            seed_worktree(repo, contract_doc([task]))
            ctrl = make_controller(repo)
            res = ctrl.run(dry_run=False, execute=True)
            self.assertEqual(res.result, "FAIL")
            self.assertTrue(res.new_evidence)
            self.assertEqual(res.new_evidence[0]["result"], "BLOCKED")
            self.assertTrue(any("BLOCKED" in e for e in res.errors), res.errors)
            self.assertEqual(ctrl.store.get("T1").state, "BLOCKED")
            self.assertNotEqual(ctrl.store.get("T1").state, "FAIL")
            self.assertNotEqual(ctrl.store.get("T1").state, "VALIDATING")

    def test_missing_binary_is_toolchain_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                allowed_tools=["python3", "git-up-missing-tool"],
                validation_commands=[{
                    "id": "v1",
                    "command": "git-up-missing-tool --version",
                    "expected_exit": 0,
                    "purpose": "missing",
                }],
            )
            seed_worktree(repo, contract_doc([task]))
            ctrl = make_controller(repo)
            res = ctrl.run(dry_run=False, execute=True)
            self.assertEqual(res.result, "FAIL")
            self.assertTrue(res.new_evidence)
            rec = res.new_evidence[0]
            self.assertEqual(rec["result"], "BLOCKED")
            self.assertEqual(rec["failure_class"], "TOOLCHAIN")
            self.assertEqual(ctrl.store.get("T1").state, "BLOCKED")

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
