"""Ambient GIT_* must not retarget observation (spec 06, 16 §9)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.repository import git_toplevel, porcelain, repo_head
from tests.support import (
    contract_doc, init_repo, make_controller, seed_worktree, write,
)


class GitIsolationTests(unittest.TestCase):
    def test_git_dir_does_not_steal_head(self):
        with tempfile.TemporaryDirectory() as td:
            target = init_repo(Path(td) / "target")
            other = init_repo(Path(td) / "other")
            seed_worktree(target)
            seed_worktree(other)
            write(other / "other-only.txt", "distinct\n")
            from tests.support import commit_all
            commit_all(other, "distinct")
            write(other / "leaked.txt", "from-other\n")
            mine = repo_head(target)
            theirs = repo_head(other)
            self.assertTrue(mine)
            self.assertNotEqual(mine, theirs)
            env = {
                "GIT_DIR": str((other / ".git").resolve()),
                "GIT_WORK_TREE": str(other.resolve()),
            }
            with unittest.mock.patch.dict(os.environ, env, clear=False):
                self.assertEqual(repo_head(target), mine)
                dirt = porcelain(target)
                self.assertNotIn("leaked.txt", dirt)
                self.assertEqual(git_toplevel(target), target.resolve())

    def test_status_alias_cannot_hide_delta(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            (home / ".gitconfig").write_text(
                "[alias]\n    status = status --untracked-files=no\n",
                encoding="utf-8",
            )
            repo = init_repo(Path(td) / "repo")
            seed_worktree(repo)
            write(repo / "hidden.txt", "untracked\n")
            with unittest.mock.patch.dict(os.environ, {"HOME": str(home)}, clear=False):
                dirt = porcelain(repo)
            self.assertIn("hidden.txt", dirt)

    def test_empty_head_dry_run_is_environment_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            write(repo / "docs" / "SPEC.md", "R1\n")
            write(repo / "src" / "out.txt", "seed\n")
            write(
                repo / "git-up.contract.json",
                json.dumps(contract_doc(), indent=2) + "\n",
            )
            # no commit → unborn / empty HEAD
            res = make_controller(repo).run(dry_run=True)
            by = {c["task_id"]: c for c in res.report["classifications"]}
            self.assertEqual(by["T1"]["effective_state"], "BLOCKED")
            self.assertEqual(by["T1"]["blocker_class"], "ENVIRONMENT")
            self.assertTrue(any("empty HEAD" in d for d in by["T1"]["detail"]))


# imported after class body so the patch.dict path is obvious
import unittest.mock  # noqa: E402


if __name__ == "__main__":
    unittest.main()
