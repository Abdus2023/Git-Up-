"""I-LOCK-1, I-LOCK-2 — lock-first and exclusive lease."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.lock import FileLock
from git_up.errors import LockAcquisitionError
from tests.support import ROOT, init_repo, make_controller, seed_worktree


class LockTests(unittest.TestCase):
    def test_I_LOCK_1_reconstruct_after_acquire(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            events = []
            ctrl = make_controller(repo, probe=events.append)
            res = ctrl.run(dry_run=False, execute=False)
            self.assertIn("acquire", events)
            self.assertIn("reconstruct", events)
            self.assertLess(events.index("acquire"), events.index("reconstruct"))
            self.assertLess(events.index("acquired"), events.index("reconstruct"))
            self.assertEqual(res.exit_code, 0)

    def test_I_LOCK_1_dry_run_has_no_acquire(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            events = []
            ctrl = make_controller(repo, probe=events.append)
            ctrl.run(dry_run=True, execute=False)
            self.assertNotIn("acquire", events)
            self.assertIn("reconstruct", events)

    def test_I_LOCK_2_second_writer_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            lock_path = repo / ".git-up" / "controller.lock"
            with FileLock(lock_path):
                proc = subprocess.run(
                    [
                        sys.executable, str(ROOT / "git-up"),
                        "--contract", str(repo / "git-up.contract.json"),
                        "--repo-root", str(repo),
                        "--state", str(repo / ".git-up" / "state.json"),
                        "--evidence", str(repo / ".git-up" / "evidence.jsonl"),
                        "--quiet",
                        "recover",
                    ],
                    capture_output=True, text=True,
                )
            self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)

    def test_second_lock_raises(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "controller.lock"
            a = FileLock(p)
            a.acquire()
            try:
                with self.assertRaises(LockAcquisitionError):
                    FileLock(p).acquire()
            finally:
                a.release()


if __name__ == "__main__":
    unittest.main()
