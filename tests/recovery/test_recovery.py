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

    def test_reconstructed_pass_via_validating(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            r1 = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(r1.result, "PASS", r1.errors)
            state_path = repo / ".git-up" / "state.json"
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            raw["tasks"][0]["state"] = "IN_PROGRESS"
            raw["tasks"][0]["validated_pass"] = False
            raw["tasks"][0]["in_progress"] = True
            state_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            r2 = make_controller(repo).run(dry_run=False, execute=False)
            states = {c["task_id"]: c["effective_state"]
                      for c in r2.report["classifications"]}
            self.assertEqual(states.get("T1"), "PASS")
            stored = json.loads(state_path.read_text(encoding="utf-8"))
            rec = stored["tasks"][0]
            self.assertEqual(rec["state"], "PASS")
            self.assertTrue(rec["validated_pass"])
            self.assertFalse(rec["in_progress"])
            self.assertTrue(any("VALIDATING" in n for n in r2.drift_notes))

    def test_crashed_in_progress_without_evidence_not_pass(self):
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
                    "state": "IN_PROGRESS",
                    "validated_pass": False,
                    "in_progress": True,
                    "last_classification": "IN_PROGRESS",
                    "evidence_refs": [],
                    "attempts": 1,
                    "updated_at": "",
                }],
            }, indent=2), encoding="utf-8")
            res = make_controller(repo).run(dry_run=False, execute=False)
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertNotEqual(states.get("T1"), "PASS")
            stored = json.loads(state.read_text(encoding="utf-8"))
            rec = next(t for t in stored["tasks"] if t["task_id"] == "T1")
            self.assertNotEqual(rec["state"], "PASS")
            self.assertFalse(rec["in_progress"])
            self.assertTrue(any("crashed" in n for n in res.drift_notes))

    def test_unknown_checkpoint_state_does_not_crash_recover(self):
        """spec 04: unknown state is refused, not coerced into a transition."""
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            r1 = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(r1.result, "PASS", r1.errors)
            state = repo / ".git-up" / "state.json"
            raw = json.loads(state.read_text(encoding="utf-8"))
            raw["tasks"][0]["state"] = "GREEN"
            raw["tasks"][0]["validated_pass"] = True
            state.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            res = make_controller(repo).run(dry_run=False, execute=False)
            self.assertEqual(res.result, "PASS", res.errors)
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertEqual(states.get("T1"), "PASS")
            stored = json.loads(state.read_text(encoding="utf-8"))
            rec = next(t for t in stored["tasks"] if t["task_id"] == "T1")
            self.assertEqual(rec["state"], "PASS")

    def test_unknown_checkpoint_schema_is_empty_store(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            state = repo / ".git-up" / "state.json"
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps({
                "schema_version": "git-up.state.v99",
                "tasks": [{
                    "task_id": "T1",
                    "state": "PASS",
                    "validated_pass": True,
                }],
            }), encoding="utf-8")
            res = make_controller(repo).run(dry_run=False, execute=False)
            self.assertEqual(res.result, "PASS", res.errors)
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertNotEqual(states.get("T1"), "PASS")

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
