"""CLI contract: inspect, plan, validate, unknown command, report lease."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.cli import main
from tests.support import init_repo, seed_worktree


def _run(argv):
    from io import StringIO
    buf = StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(argv)
    finally:
        sys.stdout = old
    text = buf.getvalue()
    data = json.loads(text) if text.strip() else {}
    return code, data


class CliTests(unittest.TestCase):
    def test_unknown_command_json(self):
        code, data = _run(["definitely-not-a-command"])
        self.assertEqual(code, 2)
        self.assertEqual(data.get("result"), "FAIL")
        self.assertTrue(data.get("errors"))

    def test_inspect_and_plan(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            c = str(repo / "git-up.contract.json")
            code, data = _run(["--contract", c, "--repo-root", str(repo), "inspect"])
            self.assertEqual(code, 0, data)
            self.assertEqual(data.get("mode"), "dry-run")
            self.assertTrue(data.get("advisory"))
            self.assertIn("T1", data.get("task_ids") or [])
            self.assertEqual(data.get("repository_identity"), "")
            self.assertTrue(data.get("document_identity"))
            code, plan = _run(["--contract", c, "--repo-root", str(repo), "plan"])
            self.assertEqual(code, 0, plan)
            self.assertEqual(plan.get("mode"), "plan")
            self.assertEqual(plan.get("ready_queue"), ["T1"])
            self.assertTrue(plan.get("expected_evidence"))

    def test_contract_validate(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            c = str(repo / "git-up.contract.json")
            code, data = _run([
                "--contract", c, "--repo-root", str(repo), "contract", "validate",
            ])
            self.assertEqual(code, 0, data)
            self.assertEqual(data.get("result"), "PASS")

    def test_report_inside_git_up_refused_on_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            dest = repo / ".git-up" / "report.json"
            code, data = _run([
                "--contract", str(repo / "git-up.contract.json"),
                "--repo-root", str(repo),
                "--report", str(dest),
                "classify",
            ])
            self.assertEqual(code, 2)
            self.assertFalse(dest.exists())
            self.assertTrue(any("lease" in e for e in data.get("errors") or []))

    def test_reconstruct_default_is_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            code, data = _run([
                "--contract", str(repo / "git-up.contract.json"),
                "--repo-root", str(repo),
                "reconstruct",
            ])
            self.assertEqual(code, 0, data)
            self.assertTrue(data.get("advisory"))
            self.assertFalse((repo / ".git-up" / "state.json").exists())
            self.assertFalse((repo / ".git-up" / "repo.identity").exists())

    def test_reconstruct_write_persists_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            code, data = _run([
                "--contract", str(repo / "git-up.contract.json"),
                "--repo-root", str(repo),
                "reconstruct", "--write",
            ])
            self.assertEqual(code, 0, data)
            self.assertFalse(data.get("advisory"))
            self.assertTrue((repo / ".git-up" / "state.json").is_file())
            self.assertTrue((repo / ".git-up" / "repo.identity").is_file())


if __name__ == "__main__":
    unittest.main()
