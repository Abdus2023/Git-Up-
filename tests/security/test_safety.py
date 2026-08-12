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

    def test_sudo_blocked_even_if_allowlisted(self):
        for exe in ("sudo", "su", "doas", "pkexec"):
            with self.subTest(exe=exe):
                with self.assertRaises(SafetyError) as ctx:
                    validate_command(f"{exe} python3", allow=[exe, "python3"])
                self.assertIn("privilege-escalation", str(ctx.exception))

    def test_prefix_allowlist_does_not_match(self):
        with self.assertRaises(SafetyError):
            validate_command("python3-evil -c pass", allow=["python3"])

    def test_exact_allowlist_ok(self):
        toks = validate_command("python3 -c pass", allow=["python3"])
        self.assertEqual(toks[0], "python3")

    def test_flag_equals_dotdot_rejected(self):
        # spec 10 §2: `..` in --flag=value must not bypass the splitter.
        with self.assertRaises(SafetyError) as ctx:
            validate_command("python3 --file=../secret", allow=["python3"])
        self.assertIn("path traversal", str(ctx.exception))

    def test_flag_equals_absolute_rejected(self):
        with self.assertRaises(SafetyError) as ctx:
            validate_command("python3 --file=/etc/passwd", allow=["python3"])
        self.assertIn("absolute", str(ctx.exception))

    def test_backslash_dotdot_rejected(self):
        with self.assertRaises(SafetyError):
            validate_command("python3 foo\\..\\secret", allow=["python3"])

    def test_relative_flag_value_ok(self):
        toks = validate_command("python3 --file=src/out.txt", allow=["python3"])
        self.assertEqual(toks[-1], "--file=src/out.txt")

    def test_shell_metacharacters_rejected(self):
        # spec 10 §2 / spec 16 §3 — including ampersand (was missing in 1.0.0).
        for ch in ";|&><`$\\":
            with self.subTest(ch=ch):
                with self.assertRaises(SafetyError):
                    validate_command(f"python3 -c {ch}", allow=["python3"])

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
