"""I-SCOPE: prohibited_scope, rename observation, untracked expansion."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.repository import parse_porcelain
from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree,
)


class ScopeTests(unittest.TestCase):
    def test_prohibited_scope_inside_target_is_violation(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                implementation_targets=["src"],
                prohibited_scope=["src/secret.txt"],
                validation_commands=[{
                    "id": "v1",
                    "command": "python3 -c \"open('src/secret.txt','w').write('x')\"",
                    "expected_exit": 0,
                    "purpose": "write prohibited",
                }],
            )
            seed_worktree(repo, contract_doc([task]))
            res = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(res.result, "FAIL")
            self.assertTrue(any("scope violation" in e for e in res.errors))
            self.assertTrue(res.new_evidence)
            self.assertEqual(res.new_evidence[0]["failure_class"], "INTEGRATION")
            self.assertIn("src/secret.txt", res.new_evidence[0]["observed_delta"])

    def test_in_target_write_is_observed_but_not_a_violation(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                implementation_targets=["src"],
                validation_commands=[{
                    "id": "v1",
                    "command": "python3 -c \"open('src/out.txt','w').write('ok')\"",
                    "expected_exit": 0,
                    "purpose": "in target",
                }],
            )
            seed_worktree(repo, contract_doc([task]))
            res = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(res.result, "PASS", res.errors)
            self.assertIn("src/out.txt", res.new_evidence[0]["observed_delta"])

    def test_parse_porcelain_rename_includes_both_paths(self):
        raw = b"R  b.txt\x00a.txt\x00?? leak/nested/x.txt\x00"
        paths = parse_porcelain(raw)
        self.assertEqual(paths, {"b.txt", "a.txt", "leak/nested/x.txt"})

    def test_rename_outside_target_is_scope_violation(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                implementation_targets=["src/out.txt"],
                required_tools=["python3", "git"],
                allowed_tools=["python3", "git"],
                validation_commands=[{
                    "id": "v1",
                    "command": "git mv src/out.txt leaked.txt",
                    "expected_exit": 0,
                    "purpose": "rename escape",
                }],
            )
            doc = contract_doc([task])
            doc["tools"].append(
                {"id": "git", "available": True, "binary": "git", "version": "2"}
            )
            seed_worktree(repo, doc)
            res = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(res.result, "FAIL")
            self.assertTrue(any("scope violation" in e for e in res.errors))
            delta = res.new_evidence[0]["observed_delta"]
            self.assertIn("leaked.txt", delta)


if __name__ == "__main__":
    unittest.main()
