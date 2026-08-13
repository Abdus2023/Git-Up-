"""Directory targets bind content (spec 06 §5 / 11 §5.7)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.contract import load_contract
from git_up.errors import ContractError
from git_up.repository import target_hashes
from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree, write,
)


class DirectoryTargetTests(unittest.TestCase):
    def test_directory_hash_is_not_absent(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            observed = target_hashes(["docs"], repo)
            self.assertTrue(str(observed["docs"]).startswith("dir:"))
            missing = target_hashes(["no-such-dir"], repo)
            self.assertIsNone(missing["no-such-dir"])
            self.assertNotEqual(observed["docs"], missing["no-such-dir"])

    def test_directory_hash_changes_with_child(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            before = target_hashes(["docs"], repo)["docs"]
            write(repo / "docs" / "SPEC.md", "changed\\n")
            after = target_hashes(["docs"], repo)["docs"]
            self.assertNotEqual(before, after)

    def test_pycache_does_not_change_directory_hash(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            before = target_hashes(["docs"], repo)["docs"]
            cache = repo / "docs" / "__pycache__"
            cache.mkdir()
            (cache / "x.pyc").write_bytes(b"\\x00")
            after = target_hashes(["docs"], repo)["docs"]
            self.assertEqual(before, after)

    def test_directory_content_change_invalidates_pass(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(implementation_targets=["src"])
            seed_worktree(repo, contract_doc([task]))
            r1 = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(r1.result, "PASS", r1.errors)
            write(repo / "src" / "out.txt", "mutated\\n")
            r2 = make_controller(repo).run(dry_run=False, execute=False)
            states = {c["task_id"]: c["effective_state"]
                      for c in r2.report["classifications"]}
            self.assertNotEqual(states.get("T1"), "PASS")

    def test_determinism_false_is_contract_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["policy"]["determinism"] = False
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(p)
            self.assertIn("determinism", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
