"""I-AUTH-1, I-PASS-4, I-PASS-5, I-HEAD-1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import (
    commit_all, contract_doc, init_repo, make_controller, minimal_task,
    seed_worktree, write,
)


class AuthorityTests(unittest.TestCase):
    def test_I_AUTH_1_missing_spec(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            (repo / "docs" / "SPEC.md").unlink()
            res = make_controller(repo).run(dry_run=True)
            states = {c["task_id"]: c for c in res.report["classifications"]}
            self.assertEqual(states["T1"]["effective_state"], "BLOCKED")
            self.assertEqual(
                states["T1"]["blocker_class"], "INSUFFICIENT_TASK_DEFINITION"
            )

    def test_I_PASS_5_dependency_fixpoint(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            t1 = minimal_task(id="T1")
            t2 = minimal_task(
                id="T2",
                dependencies=[{"ref": "T1", "required_state": "PASS"}],
            )
            reqs = [
                {"id": "R1", "specification_refs": ["docs/SPEC.md"],
                 "coverage": [
                     {"task_id": "T1", "obligations": ["all"]},
                     {"task_id": "T2", "obligations": ["all"]},
                 ]},
            ]
            seed_worktree(repo, contract_doc([t1, t2], requirements=reqs))
            res = make_controller(repo).run(dry_run=True)
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertEqual(states["T1"], "READY")
            self.assertEqual(states["T2"], "BLOCKED")

    def test_I_PASS_4_unbound_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            r1 = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(r1.result, "PASS", r1.errors)
            # Change a semantic command field → new contract_id; old evidence inert.
            doc = json.loads((repo / "git-up.contract.json").read_text())
            doc["tasks"][0]["validation_commands"][0]["command"] = "python3 -c print(0)"
            (repo / "git-up.contract.json").write_text(
                json.dumps(doc, indent=2) + "\n", encoding="utf-8"
            )
            res = make_controller(repo).run(dry_run=False, execute=False)
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertNotEqual(states.get("T1"), "PASS")

    def test_I_HEAD_1_head_drift(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            r1 = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(r1.result, "PASS", r1.errors)
            write(repo / "docs" / "SPEC.md", "R1 holds.\nchanged\n")
            commit_all(repo, " drift")
            res = make_controller(repo).run(dry_run=False, execute=False)
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertNotEqual(states.get("T1"), "PASS")


if __name__ == "__main__":
    unittest.main()
