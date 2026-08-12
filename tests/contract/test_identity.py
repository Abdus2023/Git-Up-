"""I-ID-1, I-ID-2 — contract identity stability and content sensitivity."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.contract import load_contract
from git_up.identity import contract_identity_for, source_identity
from tests.support import contract_doc, init_repo, minimal_task, seed_worktree

FROZEN_CTX = {
    "repo_identity": "repo-test",
    "head": "abc123",
    "source_identity": "",  # filled per contract
    "validator": "git-up",
    "tool_versions": {"python3": "3"},
    "timeout_seconds": 30,
}


def _ids(repo, doc):
    path = seed_worktree(repo, doc)
    c = load_contract(path)
    ctx = dict(FROZEN_CTX)
    ctx["source_identity"] = source_identity(c)
    cid = contract_identity_for(c.tasks[0], set(), ctx)
    return source_identity(c), cid


class IdentityTests(unittest.TestCase):
    def test_I_ID_1_list_reorder_stable(self):
        t1 = minimal_task(requirement_refs=["R1", "R2", "R3"])
        t2 = minimal_task(requirement_refs=["R3", "R1", "R2"])
        with tempfile.TemporaryDirectory() as td:
            s1, c1 = _ids(init_repo(Path(td) / "a"), contract_doc([t1]))
        with tempfile.TemporaryDirectory() as td:
            s2, c2 = _ids(init_repo(Path(td) / "b"), contract_doc([t2]))
        self.assertEqual(s1, s2)
        self.assertEqual(c1, c2)

    def test_I_ID_2_command_change_breaks_binding(self):
        a = minimal_task(validation_commands=[{
            "id": "v1", "command": "python3 -c pass", "expected_exit": 0,
            "purpose": "smoke",
        }])
        b = minimal_task(validation_commands=[{
            "id": "v1", "command": "python3 -c print(1)", "expected_exit": 0,
            "purpose": "smoke",
        }])
        with tempfile.TemporaryDirectory() as td:
            _, c1 = _ids(init_repo(Path(td)), contract_doc([a]))
        with tempfile.TemporaryDirectory() as td:
            _, c2 = _ids(init_repo(Path(td)), contract_doc([b]))
        self.assertNotEqual(c1, c2)


if __name__ == "__main__":
    unittest.main()
