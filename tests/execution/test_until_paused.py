"""ADR-0013: drain READY queue under one lease; residue is not a scope fail."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree,
)


class UntilPausedTests(unittest.TestCase):
    def test_until_paused_drains_dependency_chain(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            t1 = minimal_task(id="T1", priority=10)
            t2 = minimal_task(
                id="T2",
                priority=20,
                dependencies=[{"ref": "T1", "required_state": "PASS"}],
            )
            reqs = [{
                "id": "R1",
                "specification_refs": ["docs/SPEC.md"],
                "coverage": [
                    {"task_id": "T1", "obligations": ["a"]},
                    {"task_id": "T2", "obligations": ["b"]},
                ],
            }]
            seed_worktree(repo, contract_doc([t1, t2], requirements=reqs))
            drained = make_controller(repo).run(
                dry_run=False, execute=True, until_paused=True
            )
            states = {c["task_id"]: c["effective_state"]
                      for c in drained.report["classifications"]}
            self.assertEqual(drained.result, "PASS", drained.errors)
            self.assertEqual(states.get("T1"), "PASS")
            self.assertEqual(states.get("T2"), "PASS")
            self.assertEqual(drained.frontier, "PAUSED")
            self.assertEqual(drained.ready_queue, [])

    def test_single_run_does_not_drain(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            t1 = minimal_task(id="T1", priority=10)
            t2 = minimal_task(
                id="T2",
                priority=20,
                dependencies=[{"ref": "T1", "required_state": "PASS"}],
            )
            reqs = [{
                "id": "R1",
                "specification_refs": ["docs/SPEC.md"],
                "coverage": [
                    {"task_id": "T1", "obligations": ["a"]},
                    {"task_id": "T2", "obligations": ["b"]},
                ],
            }]
            seed_worktree(repo, contract_doc([t1, t2], requirements=reqs))
            res = make_controller(repo).run(
                dry_run=False, execute=True, until_paused=False
            )
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertEqual(states.get("T1"), "PASS")
            self.assertNotEqual(states.get("T2"), "PASS")

    def test_pycache_is_not_scope_violation(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                implementation_targets=["src/out.txt"],
                validation_commands=[{
                    "id": "v1",
                    "command": "python3 -c \"__import__('os').makedirs('__pycache__', exist_ok=True) or open('__pycache__/x.pyc','w').write('x')\"",
                    "expected_exit": 0,
                    "purpose": "residue",
                }],
            )
            seed_worktree(repo, contract_doc([task]))
            res = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(res.result, "PASS", res.errors)
            self.assertFalse(any("scope violation" in e for e in res.errors))


if __name__ == "__main__":
    unittest.main()
