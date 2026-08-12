"""Spec 09: contract-level authority.sources and --strict contract-shape."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import PLAN_SCHEMA, emit_contract
from git_up.cli import main
from git_up.contract import load_contract
from git_up.errors import ContractError
from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree, write,
)


class ContractSourceTests(unittest.TestCase):
    def test_missing_authority_source_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["authority"] = {"sources": [{"path": "docs/MISSING.md"}]}
            seed_worktree(repo, doc)
            res = make_controller(repo).run(dry_run=True)
            by = {c["task_id"]: c for c in res.report["classifications"]}
            self.assertEqual(by["T1"]["effective_state"], "BLOCKED")
            self.assertEqual(
                by["T1"]["blocker_class"], "INSUFFICIENT_TASK_DEFINITION"
            )
            self.assertTrue(any("MISSING.md" in d for d in by["T1"]["detail"]))

    def test_present_authority_source_allows_ready(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["authority"] = {"sources": [{"path": "docs/SPEC.md"}]}
            seed_worktree(repo, doc)
            res = make_controller(repo).run(dry_run=True)
            by = {c["task_id"]: c for c in res.report["classifications"]}
            self.assertEqual(by["T1"]["effective_state"], "READY")

    def test_garbage_authority_ref_is_contract_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["tasks"][0]["source_authority"] = [42]
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(p)
            self.assertIn("source_authority", str(ctx.exception))

    def test_strict_fails_on_traceability(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(requirement_refs=["R1", "R-GHOST"])
            seed_worktree(repo, contract_doc([task]))
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main([
                    "--contract", str(repo / "git-up.contract.json"),
                    "--repo-root", str(repo),
                    "contract", "validate", "--strict",
                ])
            finally:
                sys.stdout = old
            data = json.loads(buf.getvalue())
            self.assertEqual(code, 2, data)
            classes = {
                b["blocker_class"] for b in (data.get("strict_blockers") or [])
            }
            self.assertIn("TRACEABILITY", classes)

    def test_adapter_passes_authority_sources(self):
        plan = {
            "schema_version": PLAN_SCHEMA,
            "authority": {"sources": [{"path": "docs/SPEC.md", "anchor": "R1"}]},
            "tasks": [{"id": "T1", "title": "x"}],
        }
        doc = emit_contract(plan)
        self.assertEqual(
            doc["authority"]["sources"][0]["path"], "docs/SPEC.md"
        )

    def test_absent_sources_do_not_change_identity(self):
        from git_up.identity import source_identity
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            a = source_identity(load_contract(repo / "git-up.contract.json"))
            raw = json.loads((repo / "git-up.contract.json").read_text())
            raw["authority"] = {"sources": []}
            (repo / "git-up.contract.json").write_text(
                json.dumps(raw), encoding="utf-8"
            )
            b = source_identity(load_contract(repo / "git-up.contract.json"))
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
