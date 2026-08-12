"""I-SAFE-1, I-DRY-1, path confinement."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.errors import SafetyError
from git_up.safety import validate_command, validate_targets
from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree,
)


class SafetyTests(unittest.TestCase):
    def test_I_SAFE_1_bash_blocked_even_if_allowlisted(self):
        with self.assertRaises(SafetyError) as ctx:
            validate_command("bash -c echo hi", allow=["bash"])
        self.assertIn("shell interpreter", str(ctx.exception))

    def test_prefix_allowlist_does_not_match(self):
        with self.assertRaises(SafetyError):
            validate_command("python3-evil -c pass", allow=["python3"])

    def test_exact_allowlist_ok(self):
        toks = validate_command("python3 -c pass", allow=["python3"])
        self.assertEqual(toks[0], "python3")

    def test_git_target_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            v = validate_targets([".git/config"], td)
            self.assertTrue(v)

    def test_I_DRY_1_mute(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            ctrl = make_controller(repo)
            res = ctrl.run(dry_run=True, execute=False)
            self.assertEqual(res.result, "PASS")
            self.assertTrue(res.report.get("advisory"))
            self.assertEqual(res.report.get("mode"), "dry-run")
            self.assertFalse((repo / ".git-up" / "controller.lock").exists())
            self.assertFalse((repo / ".git-up" / "evidence.jsonl").exists())
            self.assertFalse((repo / ".git-up" / "state.json").exists())
            self.assertFalse((repo / ".git-up" / "repo.identity").exists())


if __name__ == "__main__":
    unittest.main()
