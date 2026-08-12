"""I-PASS-3, I-REC-1 — checkpoint is not authority."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import init_repo, make_controller, seed_worktree


class RecoveryTests(unittest.TestCase):
    def test_I_PASS_3_forged_checkpoint_demoted(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            state = repo / ".git-up" / "state.json"
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps({
                "schema_version": "git-up.state.v1",
                "last_checkpoint": "now",
                "repo_head": "",
                "tasks": [{
                    "task_id": "T1",
                    "state": "PASS",
                    "validated_pass": True,
                    "in_progress": False,
                    "last_classification": "PASS",
                    "evidence_refs": ["EVID-FAKE"],
                    "attempts": 1,
                    "updated_at": "",
                }],
            }, indent=2), encoding="utf-8")
            res = make_controller(repo).run(dry_run=False, execute=False)
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertNotEqual(states.get("T1"), "PASS")
            self.assertTrue(any("demoted" in n for n in res.drift_notes))

    def test_I_REC_1_corrupt_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            state = repo / ".git-up" / "state.json"
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text("{not-json", encoding="utf-8")
            res = make_controller(repo).run(dry_run=False, execute=False)
            self.assertEqual(res.result, "PASS", res.errors)
            self.assertTrue((repo / ".git-up" / "state.json").is_file())
            json.loads((repo / ".git-up" / "state.json").read_text())


if __name__ == "__main__":
    unittest.main()
