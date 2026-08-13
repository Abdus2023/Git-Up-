"""Spec 10: truncation MUST be indicated if applied."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree,
)


class TruncationTests(unittest.TestCase):
    def test_stdout_truncation_flag(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(validation_commands=[{
                "id": "v1",
                "command": "python3 -c \"print('x'*5000)\"",
                "expected_exit": 0,
                "purpose": "noise",
            }])
            seed_worktree(repo, contract_doc([task]))
            res = make_controller(repo).run(dry_run=False, execute=True)
            self.assertTrue(res.new_evidence, res.errors)
            ev = res.new_evidence[0]
            self.assertTrue(ev.get("stdout_truncated"))
            self.assertLessEqual(len(ev.get("stdout") or ""), 4000)


if __name__ == "__main__":
    unittest.main()
