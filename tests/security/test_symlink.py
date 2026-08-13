"""Symlink escape is fail-closed (spec 16)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.safety import validate_targets


class SymlinkTests(unittest.TestCase):
    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            outside = Path(td) / "outside"
            repo.mkdir()
            outside.mkdir()
            (outside / "secret").write_text("x", encoding="utf-8")
            link = repo / "link"
            os.symlink(outside, link)
            v = validate_targets(["link"], repo)
            self.assertTrue(v)
            self.assertTrue(any("symlink" in reason or "escape" in reason
                                for _, reason in v))

    def test_in_repo_symlink_ok(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "real.txt").write_text("ok", encoding="utf-8")
            os.symlink(repo / "real.txt", repo / "alias.txt")
            v = validate_targets(["alias.txt"], repo)
            self.assertEqual(v, [])


if __name__ == "__main__":
    unittest.main()
