"""Same inputs → same ids, queue, classification."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree,
)


class DeterminismTests(unittest.TestCase):
    def test_two_dry_runs_agree(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            t1 = minimal_task(id="T1", priority=20, order=2)
            t2 = minimal_task(id="T2", priority=10, order=1)
            seed_worktree(repo, contract_doc([t1, t2]))
            a = make_controller(repo).run(dry_run=True)
            b = make_controller(repo).run(dry_run=True)
            self.assertEqual(a.ready_queue, b.ready_queue)
            self.assertEqual(
                [c.to_dict() for c in a.classifications.values()],
                [c.to_dict() for c in b.classifications.values()],
            )
            ids_a = [t["contract_id"] for t in a.report["traceability"]]
            ids_b = [t["contract_id"] for t in b.report["traceability"]]
            self.assertEqual(ids_a, ids_b)
            self.assertEqual(a.ready_queue, ["T2", "T1"])


if __name__ == "__main__":
    unittest.main()
