"""Spec 06 §4 / 16 §4: every contract path is confined, including
contract-level authority.sources and requirement specification_refs."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.cli import main
from git_up.contract import load_contract, validate_confinement
from git_up.errors import ContractError
from tests.support import (
    contract_doc, init_repo, make_controller, seed_worktree,
)


class ConfinementCompleteTests(unittest.TestCase):
    def test_authority_sources_dotdot_is_confinement_error(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            # Resolves in-repo, but spec forbids a `..` component.
            doc["authority"] = {"sources": [{"path": "docs/../docs/SPEC.md"}]}
            seed_worktree(repo, doc)
            loaded = load_contract(repo / "git-up.contract.json")
            errs = validate_confinement(loaded, repo)
            self.assertTrue(any("authority.sources" in e and ".." in e for e in errs), errs)
            with self.assertRaises(ContractError) as ctx:
                make_controller(repo).run(dry_run=True)
            self.assertIn("path confinement", str(ctx.exception))

    def test_authority_sources_escape_fails_validate(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["authority"] = {"sources": [{"path": "../outside.md"}]}
            seed_worktree(repo, doc)
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main([
                    "--contract", str(repo / "git-up.contract.json"),
                    "--repo-root", str(repo),
                    "contract", "validate",
                ])
            finally:
                sys.stdout = old
            data = json.loads(buf.getvalue())
            self.assertEqual(code, 2, data)
            self.assertTrue(
                any("authority.sources" in e for e in data.get("errors") or []),
                data,
            )

    def test_requirement_specification_escape_is_confined(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["requirements"][0]["specification_refs"] = ["../secret.md"]
            seed_worktree(repo, doc)
            loaded = load_contract(repo / "git-up.contract.json")
            errs = validate_confinement(loaded, repo)
            self.assertTrue(
                any("specification_refs" in e and "secret.md" in e for e in errs),
                errs,
            )

    def test_confined_authority_source_still_ready(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["authority"] = {"sources": [{"path": "docs/SPEC.md"}]}
            seed_worktree(repo, doc)
            res = make_controller(repo).run(dry_run=True)
            by = {c["task_id"]: c for c in res.report["classifications"]}
            self.assertEqual(by["T1"]["effective_state"], "READY")


if __name__ == "__main__":
    unittest.main()
