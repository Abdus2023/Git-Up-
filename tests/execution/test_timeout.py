"""Timeout is FAIL, not PASS (spec 10)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree,
)


class TimeoutTests(unittest.TestCase):
    def test_timeout_is_fail(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(validation_commands=[{
                "id": "v1",
                "command": "python3 -c \"__import__('time').sleep(5)\"",
                "expected_exit": 0,
                "purpose": "stall",
            }])
            doc = contract_doc([task])
            doc["policy"]["timeout_seconds"] = 1
            seed_worktree(repo, doc)
            res = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(res.result, "FAIL")
            self.assertTrue(res.new_evidence)
            self.assertIsNone(res.new_evidence[0].get("exit_status"))
            self.assertEqual(res.new_evidence[0].get("result"), "FAIL")
            states = {c["task_id"]: c["effective_state"]
                      for c in res.report["classifications"]}
            self.assertNotEqual(states.get("T1"), "PASS")


if __name__ == "__main__":
    unittest.main()
